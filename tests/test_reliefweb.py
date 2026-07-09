"""ReliefWeb RSS parsing + enrich-only ingestion (ADR-0011/0014, feeds/reliefweb.md).

ReliefWeb never triggers (ADR-0001): it attaches editorial confirmation + GLIDE
to events other feeds surfaced, and creates no standalone events.
"""

from __future__ import annotations

from conftest import make_gdacs_event, make_payload, make_reliefweb_rss

from hadr.feeds import gdacs, reliefweb
from hadr.models import AlertLevel, Transition
from hadr.pipeline import process_payload


def _rw(store, notifier, config, items, **kw):
    return process_payload(
        store, notifier, config, make_reliefweb_rss(items),
        parse=reliefweb.parse, enrich_only=True, **kw,
    )


def _gdacs(store, notifier, config, feats, **kw):
    return process_payload(store, notifier, config, make_payload(feats), parse=gdacs.parse, **kw)


# --- parsing ---------------------------------------------------------------

def test_parses_glide_country_hazard_slug():
    payload = make_reliefweb_rss(
        [{"title": "Venezuela: Earthquakes - Jun 2026", "slug": "eq-2026-000093-ven",
          "glide": "EQ-2026-000093-VEN", "country": "Venezuela"}]
    )
    (rec,) = reliefweb.parse(payload)
    assert rec.source == "reliefweb"
    assert rec.source_id == "eq-2026-000093-ven"
    assert rec.glide == "EQ-2026-000093-VEN"
    assert rec.hazard_type == "EQ"  # from GLIDE prefix
    assert rec.country == "Venezuela"
    assert rec.claim_level is AlertLevel.NONE  # never triggers


def test_hazard_inferred_from_title_without_glide():
    payload = make_reliefweb_rss([{"title": "Chad: Floods - 2026", "slug": "fl-x", "glide": ""}])
    (rec,) = reliefweb.parse(payload)
    assert rec.hazard_type == "FL"


def test_tolerates_bom():
    payload = make_reliefweb_rss([{"title": "X: Earthquake", "slug": "eq-1", "glide": ""}], bom=True)
    (rec,) = reliefweb.parse(payload)
    assert rec.source_id == "eq-1"


# --- enrich-only ingestion -------------------------------------------------

def test_reliefweb_alone_creates_no_event(store, notifier, config):
    sent = _rw(store, notifier, config,
               [{"title": "Somewhere: Earthquake", "slug": "eq-2026-000999-xxx",
                 "glide": "EQ-2026-000999-XXX", "country": "Somewhere"}])
    assert sent == []
    assert store.event_count() == 0  # enrich-only: nothing to attach to -> skipped


def test_reliefweb_never_triggers_but_enriches_via_glide(store, notifier, config):
    glide = "EQ-2026-000093-VEN"
    # GDACS surfaces the event (Orange) with a GLIDE.
    _gdacs(store, notifier, config,
           [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange", glide=glide, name="Quake VEN")])
    assert store.event_count() == 1
    # ReliefWeb reports the same GLIDE — attaches, no new event, no notification.
    sent = _rw(store, notifier, config,
               [{"title": "Venezuela: Earthquakes", "slug": "eq-2026-000093-ven",
                 "glide": glide, "country": "Venezuela"}])
    assert sent == []
    assert store.event_count() == 1  # merged onto the GDACS event
    sources = {r["source"] for r in store.source_records_for_event(1)}
    assert sources == {"gdacs", "reliefweb"}


def test_reliefweb_does_not_change_alert_level(store, notifier, config):
    glide = "EQ-2026-000093-VEN"
    _gdacs(store, notifier, config,
           [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange", glide=glide)])
    _rw(store, notifier, config,
        [{"title": "Venezuela: Earthquakes", "slug": "s1", "glide": glide, "country": "Venezuela"}])
    ev = store.get_event(1)
    assert ev.alert_level is AlertLevel.ORANGE  # unchanged by enrichment
    # Only the GDACS NEW alert was ever recorded.
    assert [n["transition"] for n in store.recent_notifications()] == [int(Transition.NEW)]
