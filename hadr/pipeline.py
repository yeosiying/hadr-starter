"""Ingest pipeline: parse -> store -> dedup -> trigger -> notify.

One canonical flow used by both the live poller (hadr/run.py) and the replay
harness / tests (ADR-0012). Raw archiving happens in the caller (run.py) so
that replaying an already-archived payload doesn't re-archive it.
"""

from __future__ import annotations

from . import dedup, triggers
from .config import Config
from .feeds import usgs
from .models import Notification, SourceRecord
from .notify import Notifier
from .store import Store


def process_records(
    store: Store,
    notifier: Notifier,
    config: Config,
    records: list[SourceRecord],
    *,
    alert: bool = True,
) -> list[Notification]:
    """Run each source record through the pipeline. Returns notifications sent.

    `alert=False` stores state without notifying — the cold-start backfill path
    (ADR-0009); see the deviation note in implementation-notes.md re: alerting
    on still-active events, which needs GDACS episode levels (slice 2)."""
    sent: list[Notification] = []
    for rec in records:
        rec.event_id = dedup.resolve_event_id(store, rec)
        prev_event = store.get_event(rec.event_id)

        srid, is_new_sr, prev_sr = store.upsert_source_record(rec)
        for alias in rec.aliases:
            store.add_alias(rec.source, alias, srid)

        # Nothing materially changed since last poll -> no work (ADR-0003).
        if not is_new_sr and prev_sr is not None and prev_sr["content_hash"] == rec.content_hash:
            continue

        outcome = triggers.evaluate(
            prev_event, rec, provisional_mag_min=config.provisional_mag_min
        )

        event = prev_event
        event.alert_level = outcome.level
        event.provisional = outcome.provisional
        event.retracted = outcome.retracted
        event.title = rec.place or event.title
        event.lat = rec.lat if rec.lat is not None else event.lat
        event.lon = rec.lon if rec.lon is not None else event.lon
        if rec.glide and not event.glide:
            event.glide = rec.glide
        store.update_event(event)

        if alert:
            notif = notifier.maybe_notify(event, rec, outcome.level, outcome.transition)
            if notif is not None:
                sent.append(notif)
    return sent


def process_payload(
    store: Store,
    notifier: Notifier,
    config: Config,
    payload: bytes,
    *,
    raw_ref: str | None = None,
    alert: bool = True,
) -> list[Notification]:
    records = usgs.parse(payload, raw_ref=raw_ref)
    return process_records(store, notifier, config, records, alert=alert)
