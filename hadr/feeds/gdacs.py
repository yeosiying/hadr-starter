"""GDACS feed: fetch + parse (ADR-0005, feeds/gdacs.md).

Uses the EVENTS4APP GeoJSON event list (the feed doc's primary endpoint) rather
than the RSS feed ADR-0005 names — structured JSON avoids the RSS namespace/BOM
handling and exposes episodealertlevel directly (deviation recorded in
implementation-notes.md). EVENTS4APP returns no ETag/Last-Modified, so we can't
send conditional requests; the pipeline's content-hash prevents reprocessing.

Field notes (feeds/gdacs.md):
- `eventtype` is EQ/TC/FL/VO/DR/WF — same hazard codes we use internally.
- `eventid` is stable; `episodeid` bumps per update. RSS guid updates in place;
  the JSON list is the current snapshot.
- `alertlevel` is the lifetime max; `episodealertlevel` is the *current* level.
  We trigger on the current level (ADR-0001), so we read episodealertlevel.
- `glide` is often empty early; `country`/`iso3` name the affected country.
- geometry coordinates are [lon, lat] (GeoJSON order).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

import httpx

from ..models import AlertLevel, SourceRecord
from .usgs import FetchResult

SOURCE = "gdacs"
EVENTS4APP_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"

# GDACS hazard codes we ingest. All are stored; the alerting decision (which of
# these actually notify) is the hazard-scope gate in triggers.py (ADR-0002).
KNOWN_HAZARDS = {"EQ", "TC", "FL", "VO", "DR", "WF"}


def fetch(
    url: str = EVENTS4APP_URL,
    *,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> FetchResult:
    owns = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(url, headers={"Accept": "application/json"})
        if resp.status_code >= 400:
            return FetchResult(status="error", error=f"HTTP {resp.status_code}")
        return FetchResult(status="ok", payload=resp.content)
    except httpx.HTTPError as exc:
        return FetchResult(status="error", error=str(exc))
    finally:
        if owns:
            client.close()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # GDACS emits naive ISO like "2026-07-06T11:29:36"; treat as UTC.
        from datetime import timezone

        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _content_hash(props: dict, coords: list) -> str:
    material = json.dumps(
        {
            "episodealertlevel": props.get("episodealertlevel"),
            "alertlevel": props.get("alertlevel"),
            "episodeid": props.get("episodeid"),
            "iscurrent": props.get("iscurrent"),
            "coords": coords,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def parse(payload: bytes, *, raw_ref: str | None = None) -> list[SourceRecord]:
    """Parse an EVENTS4APP payload into SourceRecords. Tolerant of a UTF-8 BOM."""
    data = json.loads(payload.decode("utf-8-sig"))
    records: list[SourceRecord] = []
    for i, feat in enumerate(data.get("features", [])):
        props = feat.get("properties", {}) or {}
        hazard = (props.get("eventtype") or "").upper()
        if hazard not in KNOWN_HAZARDS:
            continue
        coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
        lon, lat = (coords[0], coords[1]) if len(coords) >= 2 else (None, None)
        glide = (props.get("glide") or "").strip() or None
        records.append(
            SourceRecord(
                source=SOURCE,
                source_id=str(props.get("eventid")),
                hazard_type=hazard,
                claim_level=AlertLevel.from_gdacs(props.get("episodealertlevel")),
                episode_id=(str(props["episodeid"]) if props.get("episodeid") else None),
                place=props.get("name") or props.get("eventname"),
                country=props.get("country"),
                lat=lat,
                lon=lon,
                glide=glide,
                # GDACS events don't "delete" — they go past (iscurrent=false) or
                # downgrade. Neither is a retraction (ADR-0003); only USGS emits
                # status=deleted. Store the lifecycle state without triggering one.
                status="past" if str(props.get("iscurrent")).lower() == "false" else "current",
                occurred_at=_parse_dt(props.get("fromdate")),
                source_updated_at=_parse_dt(props.get("datemodified")),
                raw_ref=f"{raw_ref}#{i}" if raw_ref else None,
                content_hash=_content_hash(props, coords),
            )
        )
    return records
