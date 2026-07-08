"""Impact-based trigger evaluation (ADR-0001), hazard scope (ADR-0002), and
re-notification semantics (ADR-0003).

The canonical event's alert state is aggregated across *all* its source claims
(CLAUDE.md convention 2): GDACS episode level is the primary impact verdict,
USGS PAGER the secondary, and a large unassessed USGS earthquake takes the
provisional path until any real assessment arrives. This is the one place state
transitions are reasoned about.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import AlertLevel, Event, Transition

# Hazard scope (ADR-0002): which hazards may alert, and at what floor.
_ALWAYS_ALERT = {"EQ", "TC", "FL"}
_STORE_ONLY = {"VO", "DR"}


def scoped_level(hazard_type: str, level: AlertLevel) -> AlertLevel:
    """Clamp a raw level to what the hazard scope permits to alert."""
    if hazard_type in _ALWAYS_ALERT:
        return level
    if hazard_type == "WF":
        return level if level >= AlertLevel.RED else AlertLevel.NONE
    # VO / DR / unknown: stored but never alertable.
    return AlertLevel.NONE


@dataclass
class TriggerOutcome:
    level: AlertLevel
    provisional: bool
    retracted: bool
    transition: Transition


def _claim(row) -> AlertLevel:
    return AlertLevel(row["claim_level"])


def aggregate(
    hazard_type: str, source_rows, *, provisional_mag_min: float
) -> tuple[AlertLevel, bool, bool]:
    """Fold all source claims into (level, provisional, deleted).

    - deleted: there are sources and every one is marked deleted (USGS only).
    - assessed: max of any source's explicit verdict (GDACS/PAGER), scope-clamped.
    - provisional: no assessment exists, but a live USGS quake is >= the
      magnitude floor — the unassessed fast path (ADR-0001).
    """
    live = [r for r in source_rows if (r["status"] or "").lower() != "deleted"]
    if source_rows and not live:
        return AlertLevel.NONE, False, True  # every source withdrawn

    assessed = max((_claim(r) for r in live), default=AlertLevel.NONE)
    has_assessment = any(_claim(r) > AlertLevel.NONE for r in live)
    provisional_candidate = any(
        r["source"] == "usgs"
        and _claim(r) == AlertLevel.NONE
        and r["mag"] is not None
        and r["mag"] >= provisional_mag_min
        for r in live
    )

    if has_assessment:
        return scoped_level(hazard_type, assessed), False, False
    if provisional_candidate:
        return scoped_level(hazard_type, AlertLevel.PROVISIONAL), True, False
    return AlertLevel.NONE, False, False


def evaluate(event: Event, source_rows, *, provisional_mag_min: float) -> TriggerOutcome:
    """Compare the event's prior persisted state to the freshly-aggregated state
    and decide the notification transition (ADR-0003)."""
    level, provisional, deleted = aggregate(
        event.hazard_type, source_rows, provisional_mag_min=provisional_mag_min
    )
    prev_level = event.alert_level
    prev_provisional = event.provisional
    prev_alertable = prev_level.is_alertable and not event.retracted

    if deleted:
        transition = Transition.RETRACTION if prev_alertable else Transition.NONE
        return TriggerOutcome(prev_level, False, True, transition)

    if not prev_alertable and level.is_alertable:
        transition = Transition.NEW
    elif prev_alertable and level.is_alertable:
        if level > prev_level:
            transition = (
                Transition.CONFIRMATION
                if prev_provisional and level >= AlertLevel.YELLOW
                else Transition.ESCALATION
            )
        else:
            transition = Transition.NONE  # same level or downgrade -> silent
    elif prev_alertable and not level.is_alertable:
        # Provisional resolving below threshold (e.g. assessed GREEN) is a
        # stand-down the user must hear (ADR-0001); a genuine downgrade is silent.
        transition = Transition.RETRACTION if prev_provisional else Transition.NONE
    else:
        transition = Transition.NONE

    return TriggerOutcome(level, provisional, False, transition)
