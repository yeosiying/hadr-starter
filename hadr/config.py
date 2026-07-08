"""Env-driven configuration (CLAUDE.md convention 3: config, not constants).

Loads a `.env` file if present (no python-dotenv dependency — a tiny parser),
then reads settings from the environment with sane defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Populate os.environ from a .env file. Existing env vars win."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    db_path: Path
    archive_dir: Path
    dashboard_path: Path
    web_host: str
    web_port: int
    usgs_feed_url: str
    usgs_poll_seconds: int
    gdacs_feed_url: str
    gdacs_poll_seconds: int
    reliefweb_enabled: bool
    reliefweb_rss_url: str
    reliefweb_poll_seconds: int
    reliefweb_appname: str  # reserved for the future JSON-API upgrade (ADR-0014)
    provisional_mag_min: float
    coalesce_minutes: int
    backfill_hours: int
    dedup_window_hours: int
    dedup_max_km: float


def load_config(dotenv_path: str = ".env") -> Config:
    _load_dotenv(dotenv_path)
    return Config(
        db_path=Path(os.environ.get("HADR_DB_PATH", "data/hadr.sqlite3")),
        archive_dir=Path(os.environ.get("HADR_ARCHIVE_DIR", "data/raw")),
        dashboard_path=Path(os.environ.get("HADR_DASHBOARD_PATH", "dashboard.html")),
        web_host=os.environ.get("HADR_WEB_HOST", "127.0.0.1"),
        web_port=int(os.environ.get("HADR_WEB_PORT", "8000")),
        usgs_feed_url=os.environ.get(
            "HADR_USGS_FEED_URL",
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
        ),
        usgs_poll_seconds=int(os.environ.get("HADR_USGS_POLL_SECONDS", "60")),
        gdacs_feed_url=os.environ.get(
            "HADR_GDACS_FEED_URL",
            "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP",
        ),
        gdacs_poll_seconds=int(os.environ.get("HADR_GDACS_POLL_SECONDS", "360")),
        reliefweb_enabled=_bool("HADR_RELIEFWEB_ENABLED", True),
        reliefweb_rss_url=os.environ.get(
            "HADR_RELIEFWEB_RSS_URL", "https://reliefweb.int/disasters/rss.xml"
        ),
        reliefweb_poll_seconds=int(os.environ.get("HADR_RELIEFWEB_POLL_SECONDS", "1800")),
        reliefweb_appname=os.environ.get("HADR_RELIEFWEB_APPNAME", "").strip(),
        provisional_mag_min=float(os.environ.get("HADR_PROVISIONAL_MAG_MIN", "6.0")),
        coalesce_minutes=int(os.environ.get("HADR_COALESCE_MINUTES", "30")),
        backfill_hours=int(os.environ.get("HADR_BACKFILL_HOURS", "72")),
        dedup_window_hours=int(os.environ.get("HADR_DEDUP_WINDOW_HOURS", "48")),
        dedup_max_km=float(os.environ.get("HADR_DEDUP_MAX_KM", "100")),
    )
