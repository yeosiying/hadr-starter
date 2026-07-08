"""Web render (ADR-0013): the page reflects store state without a socket."""

from __future__ import annotations

import dataclasses

from conftest import make_gdacs_event, make_payload, make_quake, make_reliefweb_rss

from hadr.feeds import gdacs, reliefweb, usgs
from hadr.pipeline import process_payload
from hadr.web import render_page, write_dashboard


def _usgs(store, notifier, config, feats, **kw):
    return process_payload(store, notifier, config, make_payload(feats), parse=usgs.parse, **kw)


def _gdacs(store, notifier, config, feats, **kw):
    return process_payload(store, notifier, config, make_payload(feats), parse=gdacs.parse, **kw)


def test_active_alert_appears_on_page(store, notifier, config):
    _gdacs(store, notifier, config, [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange", name="Quake near Testville")])
    html = render_page(store, config)
    assert "Current alerts (1)" in html
    assert "Quake near Testville" in html
    assert "ORANGE" in html
    assert "ALERT" in html  # the update row


def test_empty_store_shows_no_alerts_and_no_activity_banner(store, notifier, config):
    html = render_page(store, config)
    assert "Current alerts (0)" in html
    assert "No active alerts" in html
    assert "No feed activity yet" in html


def test_small_quake_not_shown_as_active(store, notifier, config):
    _usgs(store, notifier, config, [make_quake(mag=2.5)])
    html = render_page(store, config)
    assert "Current alerts (0)" in html  # stored, but below threshold


def test_degraded_feed_shows_banner(store, notifier, config):
    # A feed whose last success is far in the past reads as degraded.
    store.save_feed_state("usgs", success=True)
    store.conn.execute(
        "UPDATE feed_state SET last_success_at=? WHERE feed=?",
        ("2000-01-01T00:00:00+00:00", "usgs"),
    )
    store.conn.commit()
    html = render_page(store, config)
    assert "Feed degraded" in html
    assert "usgs" in html


def test_healthy_feed_shows_ok_banner(store, notifier, config):
    store.save_feed_state("usgs", success=True)
    html = render_page(store, config)
    assert "All feeds healthy" in html


def test_html_escaping_of_event_title(store, notifier, config):
    _gdacs(store, notifier, config, [make_gdacs_event(episodealertlevel="Red", name="<script>x</script>")])
    html = render_page(store, config)
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_live_page_autorefreshes_snapshot_does_not(store, config):
    live = render_page(store, config, live=True)
    snap = render_page(store, config, live=False)
    assert 'http-equiv="refresh"' in live
    assert "Auto-refreshes" in live
    assert 'http-equiv="refresh"' not in snap
    assert "Snapshot generated" in snap


def test_reliefweb_enrichment_badge(store, notifier, config):
    glide = "EQ-2026-000093-VEN"
    _gdacs(store, notifier, config,
           [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange", glide=glide, name="Quake VEN")])
    process_payload(
        store, notifier, config,
        make_reliefweb_rss([{"title": "Venezuela: Earthquakes", "slug": "eq-2026-000093-ven",
                             "glide": glide, "country": "Venezuela"}]),
        parse=reliefweb.parse, enrich_only=True,
    )
    html = render_page(store, config)
    assert "ReliefWeb — confirmed" in html
    assert "https://reliefweb.int/disaster/eq-2026-000093-ven" in html


def test_no_reliefweb_badge_without_enrichment(store, notifier, config):
    _gdacs(store, notifier, config, [make_gdacs_event(episodealertlevel="Red")])
    assert "ReliefWeb — confirmed" not in render_page(store, config)


def test_write_dashboard_creates_file(store, notifier, config, tmp_path):
    _gdacs(store, notifier, config, [make_gdacs_event(episodealertlevel="Red", name="Big TC")])
    cfg = dataclasses.replace(config, dashboard_path=tmp_path / "dashboard.html")
    path = write_dashboard(store, cfg)
    written = (tmp_path / "dashboard.html").read_text()
    assert path == str(tmp_path / "dashboard.html")
    assert "Big TC" in written
    assert 'http-equiv="refresh"' not in written  # static snapshot
