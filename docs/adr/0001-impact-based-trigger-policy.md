# ADR-0001: Impact-based trigger policy, not physical severity

Date: 2026-07-08 · Status: Accepted

## Context

Physical severity is a poor proxy for humanitarian relevance: an M7.5 in
empty ocean is a GDACS Green non-event, while an M6.2 under a dense city can
be a mass-casualty disaster. GDACS alert levels already model exposure ×
vulnerability, and USGS PAGER estimates fatalities/losses — but PAGER arrives
~30 min after detection and GDACS EQ alerts lag ~25 min (waiting on ShakeMap),
so a purely impact-based trigger is slow for the biggest events.

## Decision

Trigger alerts on modeled humanitarian impact:

1. **Primary**: GDACS Orange/Red, using `episodealertlevel` (current state),
   not `alertlevel` (lifetime max) — the two diverge.
2. **Secondary**: USGS PAGER yellow or worse.
3. **Fast provisional path**: USGS M≥6.0 near populated land alerts
   immediately, explicitly labeled *unassessed*; upgraded or retracted when
   GDACS/PAGER assessments arrive.
4. **ReliefWeb never triggers** — editorial content is hours–days late with
   coverage bias; it enriches and confirms existing events only.

## Consequences

- Big events alert within minutes via the provisional path, at the cost of
  occasional "unassessed → dropped" retractions (accepted noise).
- Trigger evaluation needs both feeds' state per event — reinforces the
  canonical-event model (ADR-0004).
- `mag` values across networks aren't strictly comparable (Mww/mb/ML
  saturate differently); M≥6.0 is a pragmatic threshold, kept as config.
