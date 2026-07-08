# ADR-0009: Backfill on startup; alert only still-active Orange/Red

Date: 2026-07-08 · Status: Accepted

## Context

On first boot — and every restart after downtime — events occurred while the
agent was off. "Start from now" is simplest but makes an ongoing Red-level
cyclone from yesterday invisible, which for HADR purposes is exactly the
wrong thing to miss. Blind full-backfill alerting would replay stale noise.

## Decision

On startup:

1. **Backfill** the recent window (default 72 h, config) into the store:
   USGS via the FDSN query endpoint (`updatedafter` for incremental sync;
   hard cap 20,000 results per query), GDACS via the `rss_7d` feed.
   ReliefWeb backfill only when its flag is on (ADR-0011), budget permitting.
2. Backfilled events are **store-only by default** — no alerts for things
   that already happened and ended.
3. **Exception**: events whose *current* state is GDACS Orange/Red (episode
   level) at startup time do alert — an ongoing crisis is still actionable.
4. Track last-successful-poll per feed so restarts backfill only the gap.

## Consequences

- Restart storms don't re-alert history; ongoing crises are never silently
  dropped by a reboot.
- Needs a "current state vs. historical state" distinction in trigger
  evaluation — episode alert level makes this natural for GDACS.
- FDSN and summary-feed representations of the same event differ slightly;
  the source-record layer must normalize both.
