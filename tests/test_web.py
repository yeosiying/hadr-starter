"""Web render (ADR-0013): the page reflects store state without a socket."""

from __future__ import annotations

import dataclasses

from conftest import make_gdacs_event, make_payload, make_quake, make_reliefweb_rss

from hadr.feeds import gdacs, reliefweb, usgs
from hadr.pipeline import process_payload
from hadr.web import render_event_page, render_page, write_dashboard


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
    assert "ReliefWeb — confirmed" in html          # badge on the index card
    assert 'href="/event/1"' in html                # card links to the detail page
    # The outbound ReliefWeb link now lives on the detail page, not the index.
    assert "reliefweb.int/disaster/eq-2026-000093-ven" in render_event_page(store, config, 1)


def test_no_reliefweb_badge_without_enrichment(store, notifier, config):
    _gdacs(store, notifier, config, [make_gdacs_event(episodealertlevel="Red")])
    assert "ReliefWeb — confirmed" not in render_page(store, config)


def test_active_cards_link_to_detail_page(store, notifier, config):
    _gdacs(store, notifier, config, [make_gdacs_event(episodealertlevel="Red", name="Big TC")])
    assert 'href="/event/1"' in render_page(store, config)


def test_event_detail_shows_sources_and_timeline(store, notifier, config):
    glide = "EQ-2026-000093-VEN"
    _gdacs(store, notifier, config,
           [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange", glide=glide, name="Quake VEN")])
    process_payload(
        store, notifier, config,
        make_reliefweb_rss([{"title": "Venezuela: Earthquakes", "slug": "eq-2026-000093-ven",
                             "glide": glide, "country": "Venezuela"}]),
        parse=reliefweb.parse, enrich_only=True,
    )
    page = render_event_page(store, config, 1)
    assert page is not None
    assert "Sources (2)" in page          # GDACS + ReliefWeb claims both listed
    assert "GDACS" in page and "ReliefWeb" in page
    assert glide in page                   # GLIDE shown in details
    assert "ALERT" in page                 # the NEW transition in the timeline
    assert "reliefweb.int/disaster/eq-2026-000093-ven" in page  # outbound source link


def test_event_detail_404_for_missing(store, config):
    assert render_event_page(store, config, 999) is None


def _ms_days_ago(days):
    from hadr.models import now_utc
    return int((now_utc().timestamp() - days * 86400) * 1000)


def test_recently_ended_alert_shows_in_past_week_section(store, notifier, config):
    # A provisional quake from 2 days ago that then gets deleted -> retracted.
    t = _ms_days_ago(2)
    _usgs(store, notifier, config, [make_quake(eq_id="x", mag=6.5, time_ms=t, updated_ms=t)])
    _usgs(store, notifier, config,
          [make_quake(eq_id="x", mag=6.5, status="deleted", time_ms=t, updated_ms=t + 1)])
    html = render_page(store, config)
    assert "Earlier this week — ended (1)" in html
    assert "occurred" in html          # occurred date shown on the card
    assert store.active_events() == []  # not in the current-active list


def test_notable_panel_lists_low_impact_big_quake(store, notifier, config):
    # A M6.2 that PAGER assessed GREEN: no humanitarian alert, but it should
    # appear in the "Notable seismic activity" awareness panel.
    t = _ms_days_ago(3)
    _usgs(store, notifier, config,
          [make_quake(eq_id="g1", mag=6.2, alert="green", time_ms=t, updated_ms=t,
                      place="58 km W of Tobelo, Indonesia")])
    assert store.active_events() == []          # correctly not an alert
    html = render_page(store, config)
    assert "Notable seismic activity — M6+ this week (1)" in html
    assert "M6.2" in html
    assert "Tobelo" in html


def test_notable_panel_excludes_small_and_old(store, notifier, config):
    t = _ms_days_ago(2)
    old = _ms_days_ago(30)
    _usgs(store, notifier, config, [make_quake(eq_id="s1", mag=5.4, alert="green", time_ms=t, updated_ms=t)])
    _usgs(store, notifier, config, [make_quake(eq_id="o1", mag=6.5, alert="green", time_ms=old, updated_ms=old)])
    assert store.notable_events(6.0, 7) == []   # M5.4 below floor, M6.5 too old
    assert "Notable seismic activity" not in render_page(store, config)


def test_old_ended_alert_excluded_from_past_week(store, notifier, config):
    t = _ms_days_ago(30)  # older than the 7-day window
    _usgs(store, notifier, config, [make_quake(eq_id="y", mag=6.5, time_ms=t, updated_ms=t)])
    _usgs(store, notifier, config,
          [make_quake(eq_id="y", mag=6.5, status="deleted", time_ms=t, updated_ms=t + 1)])
    assert store.recently_ended_alerts(7) == []
    assert "Earlier this week" not in render_page(store, config)


def test_write_dashboard_creates_file(store, notifier, config, tmp_path):
    _gdacs(store, notifier, config, [make_gdacs_event(episodealertlevel="Red", name="Big TC")])
    cfg = dataclasses.replace(config, dashboard_path=tmp_path / "dashboard.html")
    path = write_dashboard(store, cfg)
    written = (tmp_path / "dashboard.html").read_text()
    assert path == str(tmp_path / "dashboard.html")
    assert "Big TC" in written
    assert 'http-equiv="refresh"' not in written  # static snapshot
