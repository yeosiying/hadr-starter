"""USGS earthquake feed: fetch + parse (ADR-0005, feeds/usgs.md).

The summary GeoJSON regenerates every minute and is server-cached ~60 s, so we
poll with If-Modified-Since and treat 304 as "nothing new" (no usable ETag).
Parsing is deliberately separated from fetching so the parser can run over
archived payloads in replay tests (ADR-0012).

Feed field notes (feeds/usgs.md):
- `id` is the preferred id; `ids` is a comma-wrapped list of all ids the event
  has carried. We keep the non-preferred ones as aliases (ADR-0004) so a
  re-key doesn't create a duplicate event.
- `time`/`updated` are epoch milliseconds; `updated` > `time` means revised.
- `alert` is the PAGER colour (green/yellow/orange/red) or null.
- `status` is automatic / reviewed / deleted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import httpx

from ..models import AlertLevel, SourceRecord, epoch_ms_to_dt

SOURCE = "usgs"


@dataclass
class FetchResult:
    """Outcome of one poll. `payload` is None on 304/failure."""

    status: str  # "ok" | "not_modified" | "error"
    payload: bytes | None = None
    last_modified: str | None = None
    error: str | None = None


def fetch(
    url: str,
    *,
    if_modified_since: str | None = None,
    client: httpx.Client | None = None,
    timeout: float = 20.0,
) -> FetchResult:
    """Fetch the feed with a conditional request. Never raises for HTTP status."""
    headers = {"Accept": "application/json"}
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since
    owns = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(url, headers=headers)
        if resp.status_code == 304:
            return FetchResult(status="not_modified")
        if resp.status_code >= 400:
            return FetchResult(status="error", error=f"HTTP {resp.status_code}")
        return FetchResult(
            status="ok",
            payload=resp.content,
            last_modified=resp.headers.get("Last-Modified"),
        )
    except httpx.HTTPError as exc:  # network/timeout
        return FetchResult(status="error", error=str(exc))
    finally:
        if owns:
            client.close()


def _split_ids(ids: str | None) -> list[str]:
    """`,ci41287863,us6000tafd,` -> ['ci41287863', 'us6000tafd']."""
    if not ids:
        return []
    return [p for p in ids.split(",") if p]


def _content_hash(props: dict, coords: list) -> str:
    """Hash the fields whose change is meaningful (drives update detection).

    Deliberately excludes `updated` alone — a bumped timestamp with identical
    substance is not a change worth reprocessing."""
    material = json.dumps(
        {
            "mag": props.get("mag"),
            "place": props.get("place"),
            "alert": props.get("alert"),
            "status": props.get("status"),
            "coords": coords,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def parse(payload: bytes, *, raw_ref: str | None = None) -> list[SourceRecord]:
    """Parse a summary-feed payload into SourceRecords. Tolerant of a UTF-8 BOM."""
    data = json.loads(payload.decode("utf-8-sig"))
    records: list[SourceRecord] = []
    for i, feat in enumerate(data.get("features", [])):
        props = feat.get("properties", {}) or {}
        if props.get("type") != "earthquake":
            continue  # slice 1: earthquakes only
        coords = (feat.get("geometry") or {}).get("coordinates") or [None, None, None]
        lon, lat = coords[0], coords[1]
        depth = coords[2] if len(coords) > 2 else None
        preferred = feat.get("id")
        aliases = [x for x in _split_ids(props.get("ids")) if x != preferred]
        records.append(
            SourceRecord(
                source=SOURCE,
                source_id=preferred,
                hazard_type="EQ",
                aliases=aliases,
                claim_level=AlertLevel.from_pager(props.get("alert")),
                mag=props.get("mag"),
                place=props.get("place"),
                lat=lat,
                lon=lon,
                depth_km=depth,
                pager=props.get("alert"),
                status=props.get("status"),
                occurred_at=epoch_ms_to_dt(props.get("time")),
                source_updated_at=epoch_ms_to_dt(props.get("updated")),
                raw_ref=f"{raw_ref}#{i}" if raw_ref else None,
                content_hash=_content_hash(props, coords),
            )
        )
    return records
