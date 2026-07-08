"""GDACS parser + hazard-scope gate (feeds/gdacs.md, ADR-0002)."""

from __future__ import annotations

from conftest import make_gdacs_event, make_payload

from hadr.feeds import gdacs
from hadr.models import AlertLevel
from hadr.triggers import scoped_level


def test_parses_episode_level_and_ids():
    payload = make_payload([make_gdacs_event(eventid=999, episodeid=42, episodealertlevel="Red")])
    (rec,) = gdacs.parse(payload)
    assert rec.source == "gdacs"
    assert rec.source_id == "999"
    assert rec.episode_id == "42"
    assert rec.claim_level is AlertLevel.RED
    assert rec.country == "Testland"
    assert rec.lat == -30.0 and rec.lon == -70.0


def test_reads_episode_not_lifetime_level():
    # alertlevel (lifetime max) diverges from episodealertlevel (current).
    payload = make_payload(
        [make_gdacs_event(alertlevel="Red", episodealertlevel="Orange")]
    )
    (rec,) = gdacs.parse(payload)
    assert rec.claim_level is AlertLevel.ORANGE  # current, not the lifetime max


def test_tolerates_bom():
    payload = make_payload([make_gdacs_event(eventid=7)], bom=True)
    (rec,) = gdacs.parse(payload)
    assert rec.source_id == "7"


def test_empty_glide_becomes_none():
    payload = make_payload([make_gdacs_event(glide="")])
    (rec,) = gdacs.parse(payload)
    assert rec.glide is None


def test_past_event_is_not_deleted():
    payload = make_payload([make_gdacs_event(iscurrent="false")])
    (rec,) = gdacs.parse(payload)
    assert rec.status == "past"  # not "deleted" — GDACS doesn't retract


def test_scope_gate():
    assert scoped_level("EQ", AlertLevel.ORANGE) is AlertLevel.ORANGE
    assert scoped_level("FL", AlertLevel.RED) is AlertLevel.RED
    # Volcano/drought are stored but never alertable.
    assert scoped_level("VO", AlertLevel.RED) is AlertLevel.NONE
    assert scoped_level("DR", AlertLevel.ORANGE) is AlertLevel.NONE
    # Wildfire only at Red.
    assert scoped_level("WF", AlertLevel.ORANGE) is AlertLevel.NONE
    assert scoped_level("WF", AlertLevel.RED) is AlertLevel.RED
