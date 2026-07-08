"""Impact-based trigger evaluation (ADR-0001) + re-notification semantics
(ADR-0003).

Given an event's prior persisted state and the newest source claim, compute
the event's new alert level and the notification transition. This is the one
place state transitions are reasoned about; it reads canonical events, never
raw feed items (CLAUDE.md convention 2).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AlertLevel, Event, SourceRecord, Transition


@dataclass
class TriggerOutcome:
    level: AlertLevel
    provisional: bool
    retracted: bool
    transition: Transition


def evaluate(event: Event, rec: SourceRecord, *, provisional_mag_min: float) -> TriggerOutcome:
    prev_level = event.alert_level
    prev_provisional = event.provisional
    prev_alertable = prev_level.is_alertable and not event.retracted

    deleted = (rec.status or "").lower() == "deleted"
    pager_level = rec.alert_level()  # NONE if no PAGER yet
    is_provisional = (
        not deleted
        and pager_level == AlertLevel.NONE
        and rec.mag is not None
        and rec.mag >= provisional_mag_min
    )
    new_level = max(pager_level, AlertLevel.PROVISIONAL if is_provisional else AlertLevel.NONE)
    new_alertable = new_level.is_alertable

    # --- transition ----------------------------------------------------------
    if deleted:
        transition = (
            Transition.RETRACTION if prev_alertable else Transition.NONE
        )
        return TriggerOutcome(prev_level, False, True, transition)

    if not prev_alertable and new_alertable:
        transition = Transition.NEW
    elif prev_alertable and new_alertable:
        if new_level > prev_level:
            transition = (
                Transition.CONFIRMATION
                if prev_provisional and new_level >= AlertLevel.YELLOW
                else Transition.ESCALATION
            )
        else:
            transition = Transition.NONE  # same level or downgrade -> store silently
    elif prev_alertable and not new_alertable:
        # Fell below threshold. A provisional alert resolving to GREEN is a
        # stand-down the user must hear about (ADR-0001); a genuine downgrade
        # (e.g. YELLOW->GREEN) is stored silently (ADR-0003).
        transition = Transition.RETRACTION if prev_provisional else Transition.NONE
    else:
        transition = Transition.NONE

    return TriggerOutcome(new_level, is_provisional, False, transition)
