# Implementation notes

Kept by the agent, reviewed by you. One entry per working block.

## Decisions

### 2026-07-08 — Slice 1: USGS end-to-end (ADR-0012)

Built the thin vertical slice: poll USGS → archive raw → store → dedup →
trigger → delivery, with the multi-source schema in place from day one.
(Delivery was Telegram in this slice; changed to the web app on 2026-07-08 —
see the delivery-change entry below and ADR-0013.)

- **Package layout** (`hadr/`): `config` (env-driven), `models` (dataclasses +
  `AlertLevel`/`Transition` enums), `archive`, `store` (SQLite), `feeds/usgs`
  (fetch + parse, separable for replay), `dedup`, `triggers`, `notify`
  (delivery + coalescing — later repurposed to the web feed), `pipeline`
  (orchestration), `run` (CLI).
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

### 2026-07-08 — Slice 2: GDACS + cross-source dedup + asyncio scheduler

- **GDACS ingest** via the EVENTS4APP GeoJSON list; reads `episodealertlevel`
  (current) not `alertlevel` (lifetime max), per ADR-0001. Hazard-scope gate
  (ADR-0002) in `triggers.scoped_level`: EQ/TC/FL alert, VO/DR store-only, WF
  only at Red.
- **Cross-source aggregation**: `triggers.aggregate` folds *all* of an event's
  source claims into one level. A stored per-source `claim_level` (GDACS
  episode level or USGS PAGER, as an `AlertLevel` int) makes this
  source-agnostic. Any real assessment overrides the USGS provisional path —
  so GDACS Orange/Red confirms it and GDACS Green stands it down (both tested
  live + in unit tests).
- **Real fuzzy dedup** (`dedup._fuzzy_match`): GLIDE exact match first, else
  same hazard + time within ±48 h + haversine distance ≤ 100 km (config).
  Conservative: closest under the ceiling wins, else a new event.
- **Asyncio scheduler**: one task per feed on its own cadence, sharing one
  SQLite connection safely (all DB work on the single event-loop thread; no
  `to_thread`). Per-feed staleness/backoff retained.
- Verified: 33 tests + ruff; live GDACS replay produced exactly 1 alert (a Red
  TC) from 100 events, correctly filtering a Green-heavy feed and an Orange
  wildfire; async `run` polled both feeds and cold-start-absorbed 123 events.

### 2026-07-08 — Delivery change: Telegram push → web app (ADR-0013)

Owner revised the delivery preference before slice 3. Swapped push for a
pull-based web page.

- **Config**: dropped `HADR_TELEGRAM_*` / `HADR_DRY_RUN`; added
  `HADR_WEB_HOST` / `HADR_WEB_PORT`.
- **Notifier** no longer pushes; `maybe_notify` records the `notifications`
  row (that *is* delivery now) and logs. Transition + coalescing logic kept so
  the on-page updates feed stays readable.
- **`hadr/web.py`**: stdlib `ThreadingHTTPServer`, no framework. `render_page`
  is a pure function (testable). Shows a feed-health banner (from `feed_state`,
  ADR-0010), current active alerts, and the recent updates feed. Reads the same
  SQLite file the poller writes, in a separate process. `hadr web` command;
  binds localhost.
- ADR-0007 marked Superseded; ADR-0010 wording made delivery-agnostic;
  CONTEXT.md / QUESTIONS.md updated. The `notify()` seam made this cheap — the
  pipeline was untouched.

### 2026-07-08 — README artifact reconciliation

Aligned the repo with the artifact names in `README.md`.

- Moved `docs/PRD.html` → root **`prd.html`** (the name the README lists).
- Added **`hadr dashboard`** → writes a static **`dashboard.html`** via the
  same `render_page` renderer (`live=False`); committed an empty-state snapshot
  as the initial product artifact (`.gitignore` already un-ignores it). The
  08:30 sitrep routine (day-2 work) will regenerate it.
- Delivery serving model is unchanged (live `hadr web`, per ADR-0013); the
  static dashboard is an additional on-demand artifact, not a per-poll write.

Still outstanding from the README's artifact list (future work, not in scope
here): `system-view.html`, `goal.md`, and at least one skill.

### 2026-07-08 — Slice 3: ReliefWeb enrichment via RSS (ADR-0011, ADR-0014)

- **RSS, not the API**: the public `disasters/rss.xml` needs no appname and
  carries GLIDE + country + title + date. Shipped enrichment on it now, enabled
  by default; the appname JSON API is a documented upgrade (ADR-0014). Verified
  live: 20/20 real disasters parsed with a GLIDE; the API returns 403 as
  expected without an approved appname.
- **`hadr/feeds/reliefweb.py`**: stdlib `xml.etree` RSS parse; GLIDE/country via
  regex on the item description; hazard from GLIDE prefix or title keywords;
  source_id = disaster-link slug. `claim_level` is always NONE — never triggers.
- **Enrich-only pipeline path** (`process_records(enrich_only=True)`): attaches
  to an existing event (GLIDE first, hazard-agnostic since GLIDE is unique; then
  fuzzy geometry) or skips. No standalone events from ReliefWeb.
  `find_event_by_glide` gained an optional hazard arg for the hazard-agnostic
  join. Scheduler adds ReliefWeb only when enabled; `hadr replay --feed reliefweb`.
- **Web**: active event cards show a "📰 ReliefWeb — confirmed" link when a
  ReliefWeb source is attached.
- 8 new tests (49 total) + ruff green.

**Deviations / notes:**
- RSS hazard inference is best-effort (e.g. GLIDE `ST` "severe storm" maps to
  TC via title). Cosmetic only: matching is GLIDE-based and standalone
  ReliefWeb events are skipped, so a mis-labelled hazard cannot cause a false
  alert. The JSON API upgrade (ADR-0014) would give the real disaster type.
- ReliefWeb records never produce notifications, so they don't appear in the
  updates feed — only as the on-card enrichment badge. Intended (never triggers).

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
   GDACS's exposure model. We alert on *all* M≥6.0 unassessed quakes; the
   self-correction is now real as of slice 2 — a later GDACS Green stands the
   provisional down (tested). Residual cost: a provisional alert may fire for a
   large remote/ocean quake in the ~25 min before GDACS assesses it.

2. **Cold-start backfill is current-snapshot, store-only, no active-alerting**
   (ADR-0009). On a first-ever boot (empty store) the first poll of each feed
   is absorbed store-only. GDACS episode levels are now available, so ADR-0009's
   "alert on still-active Orange/Red" is *possible* — deliberately still
   deferred to avoid firing every currently-active Red at once on first boot;
   revisit with a "seen-before" watermark. FDSN/7-day backfill still deferred.

3. **GDACS uses EVENTS4APP GeoJSON, not RSS** (ADR-0005 names RSS). Structured
   JSON exposes `episodealertlevel` directly and avoids RSS namespace/BOM
   parsing. EVENTS4APP returns no ETag/Last-Modified, so GDACS polls are
   unconditional; the pipeline's content-hash prevents reprocessing. Cadence
   (6 min) unchanged.

4. **GDACS has no deletion signal.** EVENTS4APP `iscurrent=false` means *past*,
   not retracted (mapped to status "past"). Deletion-driven retraction stays
   USGS-only (ADR-0003); a GDACS event leaving the list is treated like an
   aged-out item, not a withdrawal.

Resolved since slice 1: the single synchronous poll loop is now the asyncio
multi-feed scheduler (ADR-0008).
