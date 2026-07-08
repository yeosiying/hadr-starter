"""Map a source record to its canonical event (ADR-0004).

Resolution order:
1. Known source id / alias -> the event that record already belongs to.
2. GLIDE exact match on an existing event.
3. Fuzzy fallback (hazard + country + +/-48h + geometry) -- STUB for slice 1.
   Single-source USGS ingest never needs it; it exists as a marked seam so
   slice 2 (GDACS) can fill it in without reshaping callers.
4. Otherwise create a new canonical event, seeded from this record.

Merging is conservative: when unsure we create a new event rather than risk a
false merge (ADR-0004).
"""

from __future__ import annotations

from .models import Event, SourceRecord
from .store import Store


def resolve_event_id(store: Store, rec: SourceRecord) -> int:
    """Return the canonical event id for `rec`, creating an event if needed."""
    existing = store.find_source_record(rec.source, rec.source_id)
    if existing is not None:
        return existing["event_id"]

    if rec.glide:
        ev = store.find_event_by_glide(rec.glide, rec.hazard_type)
        if ev is not None:
            return ev.id

    # 3. fuzzy fallback — intentionally not implemented in slice 1.
    match = _fuzzy_match(store, rec)
    if match is not None:
        return match.id

    ev = store.create_event(
        Event(
            hazard_type=rec.hazard_type,
            glide=rec.glide,
            title=rec.place,
            country=rec.country,
            lat=rec.lat,
            lon=rec.lon,
        )
    )
    return ev.id


def _fuzzy_match(store: Store, rec: SourceRecord) -> Event | None:
    """Slice-2 seam: hazard + country + time-window + geometry proximity.

    Returns None in slice 1 — USGS is the only source, so its id/alias lookup
    is sufficient and there is nothing cross-source to merge yet."""
    return None
