# Implementation notes

Kept by the agent, reviewed by you. One entry per working block.

## Decisions

### 2026-07-08 — Slice 1: USGS end-to-end (ADR-0012)

Built the thin vertical slice: poll USGS → archive raw → store → dedup →
trigger → Telegram, with the multi-source schema in place from day one.

- **Package layout** (`hadr/`): `config` (env-driven), `models` (dataclasses +
  `AlertLevel`/`Transition` enums), `archive`, `store` (SQLite), `feeds/usgs`
  (fetch + parse, separable for replay), `dedup`, `triggers`, `notify`
  (Telegram + coalescing), `pipeline` (orchestration), `run` (CLI).
- **`AlertLevel` scale** `NONE<GREEN<PROVISIONAL<YELLOW<ORANGE<RED`. GREEN
  ranks *below* PROVISIONAL on purpose so a provisional (unassessed M≥6) that
  resolves to PAGER GREEN is a stand-down, and one that resolves to YELLOW+ is
  a confirmation — matches ADR-0001/0003 without special-casing.
- **Update detection** via a content hash over material fields (mag, place,
  alert, status, coords) — a bumped `updated` timestamp alone is not
  reprocessed. Re-key handled by keeping non-preferred `ids` as aliases.
- **Tooling**: Python + uv, httpx, stdlib sqlite3, pytest, ruff.
  `./scripts/check.sh` = ruff + pytest (18 tests). Verified live against the
  real USGS feed (240 quakes parsed) and end-to-end via `hadr replay`.

## Open questions

- **Deletion detection**: slice 1 only retracts on an explicit
  `status == "deleted"`. Absence-from-feed is NOT treated as deletion (the
  `all_day` window rolls, so aging out ≠ deleted). Reliable deletion needs the
  FDSN endpoint (`includedeleted`, 409 semantics) — deferred.
- **"Near populated land"** gating for the provisional path: see deviation
  below. Confirm whether the interim (alert all M≥6.0) is acceptable until
  GDACS lands.

## Deviations

<!-- Anything built that departs from the PRD or CLAUDE.md is recorded here,
     with the reason. An undocumented deviation is a bug. -->

1. **Provisional path drops the "near populated land" filter** (ADR-0001).
   Determining populated-land proximity needs a geo/population dataset or
   GDACS's exposure model. Slice 1 alerts on *all* M≥6.0 unassessed quakes and
   relies on ADR-0001's accepted "unassessed → dropped" retraction when a later
   PAGER GREEN arrives. Self-corrects when GDACS lands (slice 2). Cost: a few
   extra provisional alerts for large remote/ocean quakes.

2. **Cold-start backfill is summary-feed-only, store-only, no active-alerting**
   (ADR-0009). On a first-ever boot (empty store) the first poll is absorbed
   store-only so we don't blast the 24h window. ADR-0009's "alert on
   still-active Orange/Red" depends on GDACS *episode* levels, which USGS
   doesn't provide — deferred to slice 2. FDSN 72h backfill also deferred.

3. **Single synchronous poll loop, not the asyncio multi-feed scheduler**
   (ADR-0008). Slice 1 has one feed; asyncio scheduling arrives with GDACS.
