"""Ingest pipeline: parse -> store -> dedup -> aggregate -> trigger -> notify.

One canonical flow shared by the live poller (hadr/run.py) and the replay
harness / tests (ADR-0012). Feed-agnostic: callers pass already-parsed source
records from any feed. Raw archiving happens in the caller so replaying an
archived payload doesn't re-archive it.
"""

from __future__ import annotations

from . import dedup, triggers
from .config import Config
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
    enrich_only: bool = False,
) -> list[Notification]:
    """Run each source record through the pipeline. Returns notifications sent.

    `alert=False` stores state without notifying — the cold-start backfill path
    (ADR-0009).

    `enrich_only=True` attaches a record to an *existing* canonical event or
    skips it — it never creates a standalone event. This is the ReliefWeb path
    (ADR-0001/0011): editorial confirmation only, so a ReliefWeb disaster with
    no matching GDACS/USGS event is archived but adds no event to the store."""
    sent: list[Notification] = []
    for rec in records:
        if enrich_only:
            event_id = dedup.find_existing_event_id(store, rec, config)
            if event_id is None:
                continue  # nothing to enrich; ReliefWeb never triggers on its own
            rec.event_id = event_id
        else:
            rec.event_id = dedup.resolve_event_id(store, rec, config)
        prev_event = store.get_event(rec.event_id)

        srid, is_new_sr, prev_sr = store.upsert_source_record(rec)
        for alias in rec.aliases:
            store.add_alias(rec.source, alias, srid)

        # Nothing materially changed for this source since last poll -> its
        # contribution to the event is unchanged, so there is no work (ADR-0003).
        if not is_new_sr and prev_sr is not None and prev_sr["content_hash"] == rec.content_hash:
            continue

        source_rows = store.source_records_for_event(rec.event_id)
        outcome = triggers.evaluate(
            prev_event, source_rows, provisional_mag_min=config.provisional_mag_min
        )

        event = prev_event
        event.alert_level = outcome.level
        event.provisional = outcome.provisional
        event.retracted = outcome.retracted
        event.title = rec.place or event.title
        event.lat = rec.lat if rec.lat is not None else event.lat
        event.lon = rec.lon if rec.lon is not None else event.lon
        if event.occurred_at is None and rec.occurred_at is not None:
            event.occurred_at = rec.occurred_at
        if rec.glide and not event.glide:
            event.glide = rec.glide  # a late GLIDE keys future cross-source merges
        if rec.country and not event.country:
            event.country = rec.country
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
    parse,
    raw_ref: str | None = None,
    alert: bool = True,
    enrich_only: bool = False,
) -> list[Notification]:
    """Parse a raw payload with the given feed `parse` function, then process."""
    records = parse(payload, raw_ref=raw_ref)
    return process_records(
        store, notifier, config, records, alert=alert, enrich_only=enrich_only
    )
