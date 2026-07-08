"""Web render (ADR-0013): the page reflects store state without a socket."""

from __future__ import annotations

from conftest import make_gdacs_event, make_payload, make_quake

from hadr.feeds import gdacs, usgs
from hadr.pipeline import process_payload
from hadr.web import render_page


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
