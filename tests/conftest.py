"""Shared test helpers: an in-memory store, a notifier, and builders for
synthetic USGS/GDACS payloads (ADR-0012 replay-style tests without live feeds)."""

from __future__ import annotations

import json

import pytest

from hadr.config import Config
from hadr.notify import Notifier
from hadr.store import Store


def make_quake(
    *,
    eq_id: str = "us1000abcd",
    ids: str | None = None,
    mag: float = 6.2,
    place: str = "10 km S of Testville",
    time_ms: int = 1_783_342_082_180,
    updated_ms: int = 1_783_342_082_180,
    alert: str | None = None,
    status: str = "automatic",
    lon: float = -70.0,
    lat: float = -30.0,
    depth: float = 12.1,
    quake_type: str = "earthquake",
) -> dict:
    return {
        "type": "Feature",
        "id": eq_id,
        "properties": {
            "mag": mag,
            "place": place,
            "time": time_ms,
            "updated": updated_ms,
            "alert": alert,
            "status": status,
            "tsunami": 0,
            "ids": ids if ids is not None else f",{eq_id},",
            "type": quake_type,
            "title": f"M {mag} - {place}",
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat, depth]},
    }


def make_gdacs_event(
    *,
    eventid: int = 1550421,
    episodeid: int = 1716583,
    eventtype: str = "EQ",
    episodealertlevel: str = "Orange",
    alertlevel: str | None = None,
    glide: str = "",
    country: str = "Testland",
    name: str = "Earthquake in Testland",
    lon: float = -70.0,
    lat: float = -30.0,
    fromdate: str = "2026-07-06T11:29:36",
    datemodified: str = "2026-07-06T12:09:48",
    iscurrent: str = "true",
) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "eventtype": eventtype,
            "eventid": eventid,
            "episodeid": episodeid,
            "glide": glide,
            "name": name,
            "alertlevel": alertlevel or episodealertlevel,
            "episodealertlevel": episodealertlevel,
            "country": country,
            "iso3": "TST",
            "fromdate": fromdate,
            "datemodified": datemodified,
            "iscurrent": iscurrent,
        },
    }


def make_payload(features: list[dict], *, bom: bool = False) -> bytes:
    doc = {
        "type": "FeatureCollection",
        "metadata": {"generated": 1_783_342_886_000, "count": len(features)},
        "features": features,
    }
    data = json.dumps(doc).encode("utf-8")
    return b"\xef\xbb\xbf" + data if bom else data


@pytest.fixture
def config() -> Config:
    return Config(
        db_path=":memory:",
        archive_dir=None,  # unused in these tests
        web_host="127.0.0.1",
        web_port=8000,
        usgs_feed_url="http://example.invalid/feed.geojson",
        usgs_poll_seconds=60,
        gdacs_feed_url="http://example.invalid/gdacs.json",
        gdacs_poll_seconds=360,
        provisional_mag_min=6.0,
        coalesce_minutes=30,
        backfill_hours=72,
        dedup_window_hours=48,
        dedup_max_km=100.0,
    )


@pytest.fixture
def store() -> Store:
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def notifier(store: Store, config: Config) -> Notifier:
    return Notifier(store, config)
