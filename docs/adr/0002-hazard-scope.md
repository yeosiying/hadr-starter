# ADR-0002: Hazard scope — global; EQ/TC/FL alert, VO/DR store-only, WF at Red

Date: 2026-07-08 · Status: Accepted

## Context

GDACS covers six hazard types (EQ, TC, FL, VO, DR, WF). Wildfire items are
~81% of the main GDACS RSS volume; droughts are slow-onset and poorly suited
to event-style alerts; volcano alerts are manually curated and rare. Alert
fatigue is the main product risk in a quiet-then-storm traffic shape.

## Decision

- Geographic scope: **global**.
- **Alert**: earthquakes (EQ), tropical cyclones (TC), floods (FL).
- **Store but never alert**: volcanoes (VO), droughts (DR).
- **Wildfires (WF)**: alert only at GDACS Red.
- Tsunami is not a separate type — GDACS folds it into the EQ score; USGS
  `tsunami:1` means "in a tsunami-message region", not "tsunami exists".

## Consequences

- GDACS ingestion must filter by hazard type before anything else, or WF
  noise dominates processing and storage attention.
- Stored-but-silent hazards keep the door open to widening scope later
  without a backfill problem.
