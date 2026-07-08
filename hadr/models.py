"""Domain model.

Two persisted entities plus a notification record (ADR-0004, ADR-0006):

- SourceRecord: one feed's claim about one event. Never overwritten by
  another source. USGS re-keying is absorbed via `aliases` (ADR-0004).
- Event: the canonical real-world disaster. Trigger/notify logic reads this,
  never raw feed items (CLAUDE.md convention 2).

AlertLevel unifies the USGS provisional path and PAGER colours into one
ordered severity scale so escalation/downgrade are simple comparisons
(ADR-0001, ADR-0003). GDACS colours slot onto the same scale in slice 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum


class AlertLevel(IntEnum):
    """Ordered severity. Alerting threshold is PROVISIONAL (see triggers.py).

    GREEN is a real "assessed, low impact" verdict and ranks *below*
    PROVISIONAL ("unassessed but large") on purpose: a provisional alert that
    resolves to GREEN is a stand-down, one that resolves to YELLOW+ is a
    confirmation.
    """

    NONE = 0
    GREEN = 1
    PROVISIONAL = 2
    YELLOW = 3
    ORANGE = 4
    RED = 5

    @classmethod
    def from_pager(cls, alert: str | None) -> "AlertLevel":
        return {
            "green": cls.GREEN,
            "yellow": cls.YELLOW,
            "orange": cls.ORANGE,
            "red": cls.RED,
        }.get((alert or "").strip().lower(), cls.NONE)

    @property
    def is_alertable(self) -> bool:
        return self >= AlertLevel.PROVISIONAL

    @property
    def label(self) -> str:
        if self is AlertLevel.PROVISIONAL:
            return "UNASSESSED"
        return self.name


def epoch_ms_to_dt(ms: int | float | None) -> datetime | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SourceRecord:
    """One source's current claim about one event."""

    source: str  # "usgs", "gdacs", "reliefweb"
    source_id: str  # preferred id at this source
    hazard_type: str  # "EQ", "TC", "FL", ...
    aliases: list[str] = field(default_factory=list)  # other ids for the same event
    event_id: int | None = None  # FK to canonical Event
    mag: float | None = None
    place: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    depth_km: float | None = None
    pager: str | None = None  # raw green/yellow/orange/red
    status: str | None = None  # automatic / reviewed / deleted
    glide: str | None = None
    occurred_at: datetime | None = None
    source_updated_at: datetime | None = None
    raw_ref: str | None = None  # archive path#index for audit (ADR-0006)
    content_hash: str | None = None  # detects meaningful change between polls

    def alert_level(self) -> AlertLevel:
        """This source's severity: max of its PAGER verdict and, for a large
        unassessed earthquake, the provisional level. Threshold check lives in
        triggers.py so the magnitude cutoff stays configurable."""
        return AlertLevel.from_pager(self.pager)


@dataclass
class Event:
    """Canonical real-world disaster (ADR-0004)."""

    hazard_type: str
    id: int | None = None
    glide: str | None = None
    title: str | None = None
    country: str | None = None
    lat: float | None = None
    lon: float | None = None
    alert_level: AlertLevel = AlertLevel.NONE  # current, across all sources
    provisional: bool = False  # currently on the unassessed M>=min path
    retracted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Transition(IntEnum):
    """Why we are (or aren't) notifying — drives ADR-0003 semantics."""

    NONE = 0  # store silently (downgrade, minor revision)
    NEW = 1  # first alert for this event
    ESCALATION = 2  # severity rose
    CONFIRMATION = 3  # provisional got a real (YELLOW+) assessment
    RETRACTION = 4  # deleted, or provisional stood down to GREEN


@dataclass
class Notification:
    event_id: int
    transition: Transition
    level: AlertLevel
    body: str
    id: int | None = None
    sent_at: datetime | None = None
    delivered: bool = False
