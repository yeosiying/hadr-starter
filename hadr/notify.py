"""Update feed: what changes about an event become entries the web app shows
(ADR-0013, ADR-0003). Delivery is pull — recording a notification *is* the
delivery; the `hadr web` server renders these entries plus current state.

Coalescing rule (per-event, not global) keeps the feed readable:
- NEW and RETRACTION always record immediately — a first alert and a stand-down
  are both important; a retraction jumps the queue.
- ESCALATION / CONFIRMATION are suppressed if the last entry for this event was
  within the coalesce window; the newer state is still persisted, so a later
  differing poll outside the window records.
- NONE never records (silent store).
"""

from __future__ import annotations

from datetime import timedelta

from .config import Config
from .models import (
    AlertLevel,
    Event,
    Notification,
    SourceRecord,
    Transition,
    datetime,
    now_utc,
)
from .store import Store

HAZARD_EMOJI = {"EQ": "🌐", "TC": "🌀", "FL": "🌊", "VO": "🌋", "DR": "🏜️", "WF": "🔥"}
_TRANSITION_VERB = {
    Transition.NEW: "ALERT",
    Transition.ESCALATION: "ESCALATION",
    Transition.CONFIRMATION: "CONFIRMED",
    Transition.RETRACTION: "STAND-DOWN",
}


def _event_url(rec: SourceRecord) -> str:
    if rec.source == "gdacs":
        return f"https://www.gdacs.org/report.aspx?eventid={rec.source_id}"
    return f"https://earthquake.usgs.gov/earthquakes/eventpage/{rec.source_id}"


def format_message(
    event: Event, rec: SourceRecord, level: AlertLevel, transition: Transition
) -> str:
    emoji = HAZARD_EMOJI.get(event.hazard_type, "⚠️")
    verb = _TRANSITION_VERB.get(transition, "UPDATE")
    lines = [f"{emoji} {verb} — {event.hazard_type} · {level.label}"]

    if rec.mag is not None:
        lines.append(f"Magnitude: M{rec.mag:.1f}")
    if rec.place:
        lines.append(f"Location: {rec.place}")
    if event.country:
        lines.append(f"Country: {event.country}")
    if rec.pager:
        lines.append(f"PAGER: {rec.pager.upper()}")
    elif rec.source == "gdacs":
        lines.append(f"GDACS: {level.label}")
    elif level is AlertLevel.PROVISIONAL:
        lines.append("Impact: unassessed (awaiting PAGER/GDACS)")
    if rec.depth_km is not None:
        lines.append(f"Depth: {rec.depth_km:.0f} km")
    if transition is Transition.RETRACTION:
        lines.append("⚠️ Prior alert retracted — see event page.")

    lines.append(_event_url(rec))
    return "\n".join(lines)


class Notifier:
    def __init__(self, store: Store, config: Config):
        self.store = store
        self.config = config

    def _within_coalesce_window(self, event_id: int) -> bool:
        last = self.store.last_notification(event_id)
        if last is None:
            return False
        sent_at = datetime.fromisoformat(last["sent_at"])
        window = timedelta(minutes=self.config.coalesce_minutes)
        return now_utc() - sent_at < window

    def maybe_notify(
        self,
        event: Event,
        rec: SourceRecord,
        level: AlertLevel,
        transition: Transition,
    ) -> Notification | None:
        if transition is Transition.NONE:
            return None

        follow_up = transition in (Transition.ESCALATION, Transition.CONFIRMATION)
        if follow_up and self._within_coalesce_window(event.id):
            return None  # coalesced; newer state already persisted

        body = format_message(event, rec, level, transition)
        notif = self.store.record_notification(
            Notification(
                event_id=event.id,
                transition=transition,
                level=level,
                body=body,
                delivered=True,  # recorded to the feed the web app reads
            )
        )
        print(f"[update] {_TRANSITION_VERB.get(transition, 'UPDATE')} "
              f"{event.hazard_type} {level.label} — {rec.place or ''}".rstrip())
        return notif

    def send_feed_health(self, feed: str, *, degraded: bool) -> None:
        """Operational log (ADR-0010): silence must be distinguishable from
        calm. The web app renders the actual banner from feed_state; this just
        records the transition to the operator log."""
        state = "degraded" if degraded else "recovered"
        print(f"[feed-health] {feed} {state}")
