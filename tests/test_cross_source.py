"""Cross-source behaviour (ADR-0001/0002/0004): GDACS triggering, hazard scope,
dedup merges, and provisional confirmation/stand-down by an assessment."""

from __future__ import annotations

import dataclasses

from conftest import make_gdacs_event, make_payload, make_quake

from hadr.feeds import gdacs, usgs
from hadr.models import AlertLevel, Transition
from hadr.notify import Notifier
from hadr.pipeline import process_payload


def usgs_run(store, notifier, config, features, **kw):
    return process_payload(
        store, notifier, config, make_payload(features), parse=usgs.parse, **kw
    )


def gdacs_run(store, notifier, config, features, **kw):
    return process_payload(
        store, notifier, config, make_payload(features), parse=gdacs.parse, **kw
    )


def _no_coalesce(store, config):
    cfg = dataclasses.replace(config, coalesce_minutes=0)
    return cfg, Notifier(store, cfg)


# --- GDACS as a primary trigger (ADR-0001) --------------------------------

def test_gdacs_orange_eq_alerts(store, notifier, config):
    sent = gdacs_run(store, notifier, config, [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange")])
    assert len(sent) == 1
    assert sent[0].transition is Transition.NEW
    assert sent[0].level is AlertLevel.ORANGE


def test_gdacs_green_does_not_alert(store, notifier, config):
    sent = gdacs_run(store, notifier, config, [make_gdacs_event(episodealertlevel="Green")])
    assert sent == []
    assert store.event_count() == 1  # stored, not alerted


# --- hazard scope (ADR-0002) ----------------------------------------------

def test_wildfire_orange_stored_not_alerted(store, notifier, config):
    sent = gdacs_run(store, notifier, config, [make_gdacs_event(eventtype="WF", episodealertlevel="Orange")])
    assert sent == []
    assert store.event_count() == 1


def test_wildfire_red_alerts(store, notifier, config):
    sent = gdacs_run(store, notifier, config, [make_gdacs_event(eventtype="WF", episodealertlevel="Red")])
    assert len(sent) == 1
    assert sent[0].level is AlertLevel.RED


def test_volcano_never_alerts(store, notifier, config):
    sent = gdacs_run(store, notifier, config, [make_gdacs_event(eventtype="VO", episodealertlevel="Red")])
    assert sent == []
    assert store.event_count() == 1


# --- dedup (ADR-0004) ------------------------------------------------------

def test_usgs_and_gdacs_merge_by_geometry(store, config):
    # Same quake: USGS provisional then GDACS Orange at the same spot/time.
    cfg, notifier = _no_coalesce(store, config)
    usgs_run(store, notifier, cfg, [make_quake(eq_id="us1", mag=6.5, lon=-70.0, lat=-30.0)])
    sent = gdacs_run(
        store, notifier, cfg,
        [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange", lon=-70.05, lat=-30.05)],
    )
    assert store.event_count() == 1  # merged, not duplicated
    assert len(sent) == 1
    assert sent[0].transition is Transition.CONFIRMATION  # provisional confirmed
    assert sent[0].level is AlertLevel.ORANGE


def test_distant_same_hazard_events_do_not_merge(store, notifier, config):
    usgs_run(store, notifier, config, [make_quake(eq_id="us1", mag=6.5, lon=-70.0, lat=-30.0)])
    gdacs_run(
        store, notifier, config,
        [make_gdacs_event(eventtype="EQ", episodealertlevel="Orange", lon=140.0, lat=40.0)],
    )
    assert store.event_count() == 2  # conservative: far apart -> separate


def test_glide_merges_across_distance(store, notifier, config):
    # GLIDE beats geometry: same GLIDE, opposite sides of the planet, one event.
    g = "EQ-2026-000123-TST"
    gdacs_run(store, notifier, config, [make_gdacs_event(eventid=1, glide=g, lon=-70.0, lat=-30.0)])
    gdacs_run(store, notifier, config, [make_gdacs_event(eventid=2, glide=g, lon=140.0, lat=40.0)])
    assert store.event_count() == 1


def test_provisional_stood_down_by_gdacs_green(store, config):
    cfg, notifier = _no_coalesce(store, config)
    usgs_run(store, notifier, cfg, [make_quake(eq_id="us1", mag=6.5, lon=-70.0, lat=-30.0)])
    sent = gdacs_run(
        store, notifier, cfg,
        [make_gdacs_event(eventtype="EQ", episodealertlevel="Green", lon=-70.0, lat=-30.0)],
    )
    assert store.event_count() == 1
    assert len(sent) == 1
    assert sent[0].transition is Transition.RETRACTION
    assert store.get_event(1).alert_level is AlertLevel.GREEN
