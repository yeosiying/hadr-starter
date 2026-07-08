"""End-to-end pipeline: trigger + re-notification semantics (ADR-0001/0003)
and dedup/re-key handling (ADR-0004), driven by replayed payloads (ADR-0012)."""

from __future__ import annotations

import dataclasses

from conftest import make_payload, make_quake

from hadr.models import AlertLevel, Transition
from hadr.notify import Notifier
from hadr.pipeline import process_payload


def _no_coalesce(store, config):
    """Config + notifier with a zero coalesce window (immediate follow-ups)."""
    cfg = dataclasses.replace(config, coalesce_minutes=0)
    return cfg, Notifier(store, cfg)


def run(store, notifier, config, features, **kw):
    return process_payload(store, notifier, config, make_payload(features), **kw)


# --- new alerts ------------------------------------------------------------

def test_provisional_alert_on_big_unassessed_quake(store, notifier, config):
    sent = run(store, notifier, config, [make_quake(mag=6.2, alert=None)])
    assert len(sent) == 1
    assert sent[0].transition is Transition.NEW
    assert sent[0].level is AlertLevel.PROVISIONAL
    ev = store.get_event(sent[0].event_id)
    assert ev.provisional is True
    assert ev.alert_level is AlertLevel.PROVISIONAL


def test_small_quake_stored_but_not_alerted(store, notifier, config):
    sent = run(store, notifier, config, [make_quake(mag=3.0, alert=None)])
    assert sent == []
    assert store.event_count() == 1  # stored (ADR-0002), just silent


def test_pager_yellow_alerts_immediately(store, notifier, config):
    sent = run(store, notifier, config, [make_quake(mag=5.1, alert="yellow")])
    assert len(sent) == 1
    assert sent[0].level is AlertLevel.YELLOW


def test_identical_repoll_does_not_realert(store, notifier, config):
    q = make_quake(mag=6.2, alert=None)
    run(store, notifier, config, [q])
    sent2 = run(store, notifier, config, [q])
    assert sent2 == []  # content unchanged -> no work (ADR-0003)


# --- update transitions ----------------------------------------------------

def test_provisional_confirmed_by_pager(store, config):
    cfg, notifier = _no_coalesce(store, config)
    run(store, notifier, cfg, [make_quake(eq_id="x", mag=6.2, alert=None, updated_ms=1)])
    sent = run(
        store, notifier, cfg,
        [make_quake(eq_id="x", mag=6.2, alert="yellow", updated_ms=2)],
    )
    assert len(sent) == 1
    assert sent[0].transition is Transition.CONFIRMATION
    assert sent[0].level is AlertLevel.YELLOW
    assert store.get_event(sent[0].event_id).provisional is False


def test_provisional_stood_down_to_green(store, config):
    cfg, notifier = _no_coalesce(store, config)
    run(store, notifier, cfg, [make_quake(eq_id="x", mag=6.2, alert=None, updated_ms=1)])
    sent = run(
        store, notifier, cfg,
        [make_quake(eq_id="x", mag=6.2, alert="green", updated_ms=2)],
    )
    assert len(sent) == 1
    assert sent[0].transition is Transition.RETRACTION
    ev = store.get_event(sent[0].event_id)
    assert ev.alert_level is AlertLevel.GREEN


def test_escalation_yellow_to_orange(store, config):
    cfg, notifier = _no_coalesce(store, config)
    run(store, notifier, cfg, [make_quake(eq_id="x", mag=5.0, alert="yellow", updated_ms=1)])
    sent = run(
        store, notifier, cfg,
        [make_quake(eq_id="x", mag=5.0, alert="orange", updated_ms=2)],
    )
    assert len(sent) == 1
    assert sent[0].transition is Transition.ESCALATION
    assert sent[0].level is AlertLevel.ORANGE


def test_downgrade_orange_to_yellow_is_silent(store, config):
    cfg, notifier = _no_coalesce(store, config)
    run(store, notifier, cfg, [make_quake(eq_id="x", mag=5.0, alert="orange", updated_ms=1)])
    sent = run(
        store, notifier, cfg,
        [make_quake(eq_id="x", mag=5.0, alert="yellow", updated_ms=2)],
    )
    assert sent == []  # downgrade stored silently (ADR-0003)
    assert store.get_event(1).alert_level is AlertLevel.YELLOW


def test_deletion_triggers_retraction(store, notifier, config):
    run(store, notifier, config, [make_quake(eq_id="x", mag=6.2, alert=None, updated_ms=1)])
    sent = run(
        store, notifier, config,
        [make_quake(eq_id="x", mag=6.2, status="deleted", updated_ms=2)],
    )
    assert len(sent) == 1
    assert sent[0].transition is Transition.RETRACTION
    assert store.get_event(sent[0].event_id).retracted is True


# --- coalescing ------------------------------------------------------------

def test_followups_coalesced_within_window(store, notifier, config):
    # Default 30-min window: an escalation right after the initial alert is
    # suppressed (state still persists).
    run(store, notifier, config, [make_quake(eq_id="x", mag=5.0, alert="yellow", updated_ms=1)])
    sent = run(
        store, notifier, config,
        [make_quake(eq_id="x", mag=5.0, alert="orange", updated_ms=2)],
    )
    assert sent == []
    assert store.get_event(1).alert_level is AlertLevel.ORANGE  # persisted anyway


def test_retraction_ignores_coalesce_window(store, notifier, config):
    # A deletion right after the alert still sends — retractions jump the queue.
    run(store, notifier, config, [make_quake(eq_id="x", mag=6.2, alert=None, updated_ms=1)])
    sent = run(
        store, notifier, config,
        [make_quake(eq_id="x", mag=6.2, status="deleted", updated_ms=2)],
    )
    assert len(sent) == 1
    assert sent[0].transition is Transition.RETRACTION


# --- dedup / re-key --------------------------------------------------------

def test_rekey_does_not_duplicate_event(store, notifier, config):
    # Same quake, preferred id flips from ci111 to us222 (ADR-0004).
    run(store, notifier, config, [make_quake(eq_id="ci111", ids=",ci111,us222,", mag=6.2)])
    run(store, notifier, config, [make_quake(eq_id="us222", ids=",ci111,us222,", mag=6.2)])
    assert store.event_count() == 1
    a = store.find_source_record("usgs", "ci111")
    b = store.find_source_record("usgs", "us222")
    assert a["id"] == b["id"]


# --- cold start ------------------------------------------------------------

def test_backfill_stores_without_alerting(store, notifier, config):
    sent = run(store, notifier, config, [make_quake(mag=7.0, alert="red")], alert=False)
    assert sent == []
    assert store.event_count() == 1  # absorbed store-only (ADR-0009)
