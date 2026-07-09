# ADR-0004: Canonical events with per-source claims; GLIDE-first conservative dedup

Date: 2026-07-08 · Status: Accepted

## Context

The same real-world disaster appears in multiple feeds under different IDs.
GLIDE numbers are the intended cross-reference key (nominally required on
ReliefWeb disasters, present on GDACS), but the GDACS `glide` field is often
empty early in an event's life — exactly when dedup decisions must be made.

## Decision

- One **canonical event** row per real-world disaster; each feed's data hangs
  underneath as **per-source claims** (`source_records`), never overwriting
  each other.
- Matching order: **GLIDE exact match first**; fuzzy fallback on
  hazard type + country + time window (±48 h) + geometry proximity.
- **Conservative merging**: when in doubt, keep events separate. A false
  merge (two disasters presented as one) is worse than a missed merge (one
  disaster shown twice), and un-merging is much harder than merging late.
- USGS re-keying handled inside the source layer: keep old IDs (from the
  `ids` list) as aliases of the same source record.

## Consequences

- Trigger and notification logic reads canonical events, never raw feed
  items — a single place to reason about state transitions.
- Late GLIDE arrival can reveal that two canonical events are one; support a
  merge operation (fold claims, keep both notification histories).
- Fuzzy thresholds (±48 h, geometry distance) are config, tuned via replay
  fixtures (ADR-0012).
