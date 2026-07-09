# Goal

**One HADR-interested person should learn about a humanitarian-relevant
disaster without watching three websites — and should be able to trust that
no news is genuinely no news.**

## The one sentence

A single always-on service polls GDACS, USGS, and ReliefWeb, merges them into
one canonical event per real-world disaster, and publishes what matters to a
local web page — alerting on *modeled humanitarian impact*, not raw physical
severity.

## Who it's for

The repo owner, alone. No team, no accounts. They open a local page
(`hadr web`) on demand; a morning snapshot is written to `dashboard.html` at
08:30 (Asia/Singapore).

## What "done well" means (success criteria)

1. **Right signal.** Alerts fire on humanitarian impact — GDACS Orange/Red,
   USGS PAGER yellow+, and a fast provisional path for large unassessed
   quakes — not on every M4 or every wildfire. (ADR-0001, ADR-0002)
2. **One event, many sources.** The same disaster from three feeds shows up
   once, with each source's claim underneath and a GLIDE/geometry join.
   (ADR-0004)
3. **Honest about change.** Escalations, provisional confirmations, and
   retractions re-notify; downgrades and noise are stored silently.
   (ADR-0003)
4. **Trustworthy silence.** If a feed goes dark, the page says so (a degraded
   banner). Quiet + no banner = genuinely calm, not broken. (ADR-0010)
5. **Reproducible.** Every payload is archived before parsing, so any bug is
   replayable and any alert is auditable. (ADR-0006, ADR-0012)

## Explicit non-goals

- Not a push service, not multi-user, not publicly hosted (localhost only).
- Not a severity ranking of the world — ReliefWeb volume ≠ importance, and we
  never treat physical magnitude as impact.
- Not a forecasting or analysis tool — it reports what the feeds assert.
- Volcanoes/droughts are stored but never alerted; wildfires only at Red.

## How we'll know it's working

Point it at the live feeds. Within minutes a real M6.5 near people produces a
provisional alert that a later GDACS/PAGER assessment confirms or stands down;
a Green-heavy, wildfire-heavy GDACS feed produces near-silence; and killing a
feed's connectivity turns the page's health banner red. All three have been
exercised against the real feeds (see `implementation-notes.md`).
