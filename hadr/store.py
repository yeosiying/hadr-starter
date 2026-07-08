"""SQLite event store (ADR-0006).

Three core tables — events, source_records, notifications — plus source_aliases
(USGS re-keying, ADR-0004) and feed_state (conditional requests + staleness,
ADR-0005/0010). Schema is multi-source from day one though slice 1 only writes
USGS rows (ADR-0012).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .models import AlertLevel, Event, Notification, SourceRecord, now_utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY,
    hazard_type  TEXT NOT NULL,
    glide        TEXT,
    title        TEXT,
    country      TEXT,
    lat          REAL,
    lon          REAL,
    alert_level  INTEGER NOT NULL DEFAULT 0,
    provisional  INTEGER NOT NULL DEFAULT 0,
    retracted    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_records (
    id                INTEGER PRIMARY KEY,
    event_id          INTEGER NOT NULL REFERENCES events(id),
    source            TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    hazard_type       TEXT NOT NULL,
    mag               REAL,
    place             TEXT,
    country           TEXT,
    lat               REAL,
    lon               REAL,
    depth_km          REAL,
    pager             TEXT,
    status            TEXT,
    glide             TEXT,
    occurred_at       TEXT,
    source_updated_at TEXT,
    raw_ref           TEXT,
    content_hash      TEXT,
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL,
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS source_aliases (
    source           TEXT NOT NULL,
    alias            TEXT NOT NULL,
    source_record_id INTEGER NOT NULL REFERENCES source_records(id),
    PRIMARY KEY (source, alias)
);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY,
    event_id    INTEGER NOT NULL REFERENCES events(id),
    transition  INTEGER NOT NULL,
    level       INTEGER NOT NULL,
    body        TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS feed_state (
    feed                 TEXT PRIMARY KEY,
    etag                 TEXT,
    last_modified        TEXT,
    last_success_at      TEXT,
    last_attempt_at      TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    degraded_notified    INTEGER NOT NULL DEFAULT 0
);
"""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- events ------------------------------------------------------------

    def create_event(self, ev: Event) -> Event:
        now = now_utc()
        cur = self.conn.execute(
            """INSERT INTO events
               (hazard_type, glide, title, country, lat, lon,
                alert_level, provisional, retracted, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ev.hazard_type, ev.glide, ev.title, ev.country, ev.lat, ev.lon,
                int(ev.alert_level), int(ev.provisional), int(ev.retracted),
                _iso(now), _iso(now),
            ),
        )
        self.conn.commit()
        ev.id = cur.lastrowid
        ev.created_at = ev.updated_at = now
        return ev

    def update_event(self, ev: Event) -> None:
        ev.updated_at = now_utc()
        self.conn.execute(
            """UPDATE events SET
                 glide=?, title=?, country=?, lat=?, lon=?,
                 alert_level=?, provisional=?, retracted=?, updated_at=?
               WHERE id=?""",
            (
                ev.glide, ev.title, ev.country, ev.lat, ev.lon,
                int(ev.alert_level), int(ev.provisional), int(ev.retracted),
                _iso(ev.updated_at), ev.id,
            ),
        )
        self.conn.commit()

    def event_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]

    def get_event(self, event_id: int) -> Event | None:
        row = self.conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return _row_to_event(row) if row else None

    def find_event_by_glide(self, glide: str, hazard_type: str) -> Event | None:
        row = self.conn.execute(
            "SELECT * FROM events WHERE glide=? AND hazard_type=?",
            (glide, hazard_type),
        ).fetchone()
        return _row_to_event(row) if row else None

    # --- source records ----------------------------------------------------

    def find_source_record(self, source: str, source_id: str) -> sqlite3.Row | None:
        row = self.conn.execute(
            "SELECT * FROM source_records WHERE source=? AND source_id=?",
            (source, source_id),
        ).fetchone()
        if row:
            return row
        # Fall back to alias lookup (USGS preferred-id re-keying, ADR-0004).
        alias = self.conn.execute(
            "SELECT source_record_id FROM source_aliases WHERE source=? AND alias=?",
            (source, source_id),
        ).fetchone()
        if alias:
            return self.conn.execute(
                "SELECT * FROM source_records WHERE id=?", (alias["source_record_id"],)
            ).fetchone()
        return None

    def upsert_source_record(
        self, rec: SourceRecord
    ) -> tuple[int, bool, sqlite3.Row | None]:
        """Insert or update. Returns (source_record_id, is_new, previous_row)."""
        now = now_utc()
        existing = self.find_source_record(rec.source, rec.source_id)
        if existing is None:
            cur = self.conn.execute(
                """INSERT INTO source_records
                   (event_id, source, source_id, hazard_type, mag, place, country,
                    lat, lon, depth_km, pager, status, glide, occurred_at,
                    source_updated_at, raw_ref, content_hash, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec.event_id, rec.source, rec.source_id, rec.hazard_type, rec.mag,
                    rec.place, rec.country, rec.lat, rec.lon, rec.depth_km, rec.pager,
                    rec.status, rec.glide, _iso(rec.occurred_at),
                    _iso(rec.source_updated_at), rec.raw_ref, rec.content_hash,
                    _iso(now), _iso(now),
                ),
            )
            self.conn.commit()
            return cur.lastrowid, True, None

        srid = existing["id"]
        self.conn.execute(
            """UPDATE source_records SET
                 source_id=?, hazard_type=?, mag=?, place=?, country=?, lat=?, lon=?,
                 depth_km=?, pager=?, status=?, glide=?, occurred_at=?,
                 source_updated_at=?, raw_ref=?, content_hash=?, last_seen=?
               WHERE id=?""",
            (
                rec.source_id, rec.hazard_type, rec.mag, rec.place, rec.country,
                rec.lat, rec.lon, rec.depth_km, rec.pager, rec.status, rec.glide,
                _iso(rec.occurred_at), _iso(rec.source_updated_at), rec.raw_ref,
                rec.content_hash, _iso(now), srid,
            ),
        )
        self.conn.commit()
        return srid, False, existing

    def add_alias(self, source: str, alias: str, source_record_id: int) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO source_aliases (source, alias, source_record_id)
               VALUES (?,?,?)""",
            (source, alias, source_record_id),
        )
        self.conn.commit()

    # --- notifications -----------------------------------------------------

    def record_notification(self, n: Notification) -> Notification:
        n.sent_at = n.sent_at or now_utc()
        cur = self.conn.execute(
            """INSERT INTO notifications
               (event_id, transition, level, body, sent_at, delivered)
               VALUES (?,?,?,?,?,?)""",
            (n.event_id, int(n.transition), int(n.level), n.body,
             _iso(n.sent_at), int(n.delivered)),
        )
        self.conn.commit()
        n.id = cur.lastrowid
        return n

    def last_notification(self, event_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT * FROM notifications WHERE event_id=?
               ORDER BY sent_at DESC LIMIT 1""",
            (event_id,),
        ).fetchone()

    def notification_count(self, event_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) c FROM notifications WHERE event_id=?", (event_id,)
        ).fetchone()["c"]

    # --- feed state --------------------------------------------------------

    def get_feed_state(self, feed: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM feed_state WHERE feed=?", (feed,)
        ).fetchone()

    def save_feed_state(
        self,
        feed: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        success: bool | None = None,
        degraded_notified: bool | None = None,
    ) -> None:
        now = _iso(now_utc())
        row = self.get_feed_state(feed)
        if row is None:
            self.conn.execute(
                """INSERT INTO feed_state
                   (feed, etag, last_modified, last_success_at, last_attempt_at,
                    consecutive_failures, degraded_notified)
                   VALUES (?,?,?,?,?,?,?)""",
                (feed, etag, last_modified,
                 now if success else None, now,
                 0 if success else 1,
                 int(bool(degraded_notified))),
            )
            self.conn.commit()
            return
        fails = row["consecutive_failures"]
        if success is True:
            fails = 0
        elif success is False:
            fails += 1
        self.conn.execute(
            """UPDATE feed_state SET
                 etag=COALESCE(?, etag),
                 last_modified=COALESCE(?, last_modified),
                 last_success_at=?,
                 last_attempt_at=?,
                 consecutive_failures=?,
                 degraded_notified=?
               WHERE feed=?""",
            (
                etag, last_modified,
                now if success else row["last_success_at"],
                now, fails,
                int(bool(degraded_notified)) if degraded_notified is not None
                else row["degraded_notified"],
                feed,
            ),
        )
        self.conn.commit()


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        hazard_type=row["hazard_type"],
        glide=row["glide"],
        title=row["title"],
        country=row["country"],
        lat=row["lat"],
        lon=row["lon"],
        alert_level=AlertLevel(row["alert_level"]),
        provisional=bool(row["provisional"]),
        retracted=bool(row["retracted"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )
