"""Alert delivery: compact Telegram messages with per-event coalescing
(ADR-0007, ADR-0003).

Coalescing rule (per-event, not global):
- NEW and RETRACTION always send immediately — a first alert and a stand-down
  are both time-critical; a retraction jumps the queue.
- ESCALATION / CONFIRMATION are suppressed if the last notification for this
  event was within the coalesce window; the newer state is still persisted, so
  a later differing poll outside the window will notify.
- NONE never sends (silent store).
"""

from __future__ import annotations

from datetime import timedelta

import httpx

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
        delivered = self._deliver(body)
        return self.store.record_notification(
            Notification(
                event_id=event.id,
                transition=transition,
                level=level,
                body=body,
                delivered=delivered,
            )
        )

    def _deliver(self, body: str) -> bool:
        if self.config.dry_run:
            print("\n--- [DRY RUN] Telegram alert ---")
            print(body)
            print("--- end ---")
            return False
        return self._send_telegram(body)

    def _send_telegram(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        try:
            resp = httpx.post(
                url,
                json={
                    "chat_id": self.config.telegram_chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=15.0,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def send_feed_health(self, feed: str, *, degraded: bool) -> None:
        """Operational notice (ADR-0010): silence must be distinguishable from
        calm. Exempt from per-event coalescing."""
        if degraded:
            body = f"🔌 Feed degraded: {feed} has not returned fresh data. Alerts may be delayed."
        else:
            body = f"✅ Feed recovered: {feed} is responding again."
        self._deliver(body)
