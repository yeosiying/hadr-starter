# ADR-0012: Thin vertical slice first; replay-fixture testing

Date: 2026-07-08 · Status: Accepted

## Context

Two independent sequencing questions with one theme — time to real feedback.
Build order: all-feeds-store-only-first watches data longer before alerting;
full-scope-at-once maximizes simultaneous debugging. Testing: the system's
hard parts are not parsers but cross-feed dedup and update/retraction
handling, which live tests can't reproduce on demand and unit tests on
parsers don't reach.

## Decision

**Sequencing — thin vertical slice:**

1. **Slice 1 (USGS end-to-end)**: poll summary feed → raw archive → source
   records → canonical events → trigger (provisional M≥6.0 path + PAGER) →
   delivery. The dedup-ready schema (ADR-0004) ships in this slice even with
   one source. (Delivery was Telegram at the time of writing; now the web
   page — ADR-0013.)
2. **Slice 2**: GDACS ingestion + the full impact-based trigger policy +
   cross-source dedup for real.
3. **Slice 3**: ReliefWeb enrichment when the flag/appname lands (ADR-0011).

**Testing — replay fixtures:**

- The raw payload archive (ADR-0006) is the fixture corpus. Tests replay
  recorded payloads through ingest → dedup → trigger → (mock) notify and
  assert on store state and emitted notifications.
- Deliberately collect the pathological cases as fixtures: UTF-8 BOM before
  `<?xml`, USGS magnitude revisions, preferred-ID re-keying, event deletion,
  GDACS in-place guid updates, `alertlevel` vs `episodealertlevel`
  divergence, empty GLIDE fields.
- Live-feed smoke test exists but is manual/optional, never CI-gating.

## Consequences

- First real alert arrives after slice 1 — days, not weeks — and every later
  slice rides an already-proven pipeline.
- Dedup logic is only *exercised* from slice 2, but its schema exists from
  day one, avoiding a migration.
- Fixture collection is an ongoing habit: when a weird payload breaks
  something in production, it becomes a test case.
