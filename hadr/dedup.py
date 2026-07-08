"""Map a source record to its canonical event (ADR-0004).

Resolution order:
1. Known source id / alias -> the event that record already belongs to.
2. GLIDE exact match on an existing event.
3. Fuzzy fallback: same hazard + time within +/-window + geometry within
   `max_km`. Conservative — the closest candidate under the distance ceiling
   wins; if none qualify we create a new event rather than risk a false merge
   (a false merge is worse than a missed one, ADR-0004).
4. Otherwise create a new canonical event, seeded from this record.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from .config import Config
from .models import Event, SourceRecord
from .store import Store

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def resolve_event_id(store: Store, rec: SourceRecord, config: Config) -> int:
    """Return the canonical event id for `rec`, creating an event if needed."""
    existing = store.find_source_record(rec.source, rec.source_id)
    if existing is not None:
        return existing["event_id"]

    if rec.glide:
        ev = store.find_event_by_glide(rec.glide, rec.hazard_type)
        if ev is not None:
            return ev.id

    match = _fuzzy_match(store, rec, config)
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
            occurred_at=rec.occurred_at,
        )
    )
    return ev.id


def _fuzzy_match(store: Store, rec: SourceRecord, config: Config) -> Event | None:
    """Closest same-hazard event within the time window and distance ceiling."""
    if rec.lat is None or rec.lon is None:
        return None
    candidates = store.candidate_events(
        rec.hazard_type, rec.occurred_at, config.dedup_window_hours
    )
    best: Event | None = None
    best_km = config.dedup_max_km
    for row in candidates:
        if row["lat"] is None or row["lon"] is None:
            continue
        km = haversine_km(rec.lat, rec.lon, row["lat"], row["lon"])
        if km <= best_km:
            best_km = km
            best = store.get_event(row["id"])
    return best
