# ADR-0003: Re-notification semantics with per-event coalescing

Date: 2026-07-08 · Status: Accepted

## Context

Events are mutable claims: USGS revises magnitudes/locations for days,
re-keys preferred IDs, and deletes events; GDACS episodes escalate and
de-escalate; PAGER colors get upgraded. Notifying on every change floods the
user; notifying on none hides escalations and false alarms. Traffic is
quiet-then-storm — one major EQ yields an initial alert, PAGER upgrade,
GDACS episode updates, and aftershocks within an hour — so fatigue policy
matters more than detection.

## Decision

Re-notify on exactly three transitions:

1. **Escalation** — alert level rises (e.g. Orange→Red, PAGER yellow→orange).
2. **Provisional confirmation** — an unassessed M≥6.0 alert gets its
   GDACS/PAGER assessment.
3. **Retraction** — event deleted or provisional alert dropped; the user
   must learn a prior alert is void.

Silently store: downgrades, magnitude/position tweaks, new ReliefWeb reports.

**Throttling (per-event, not global)**: genuinely new events always alert
immediately. Follow-up notifications for the same canonical event are
coalesced to at most one per 30 minutes (config), sending the latest state.
Aftershocks that independently pass the trigger policy are new events, not
follow-ups.

## Consequences

- Requires a `notifications` table recording what was sent per event, and a
  pending-coalesce buffer.
- A retraction arriving inside the coalesce window should jump the queue —
  voiding a false alert is time-sensitive.
- No global rate cap in MVP; revisit if a multi-event storm (regional floods)
  proves noisy.
