# CONTEXT — HADR Monitoring Agent

Single source of truth for what this product is and why it's shaped this way.
Decisions are recorded in `docs/adr/`; open questions in `QUESTIONS.md`.
Verified feed/API facts date from 2026-07-07 research.

## Problem

A HADR-interested single user wants to know about humanitarian-relevant
disasters without watching three websites (GDACS, USGS, ReliefWeb). Nothing
pushes — all three must be polled — and the interesting signal is
*humanitarian impact*, not physical severity (an M7.5 in empty ocean is a
GDACS Green non-event).

## User

One person (the repo owner), who **visits a local web page** to see current
alerts on demand ([ADR-0013](docs/adr/0013-web-app-pull-delivery.md), which
supersedes the original Telegram-push decision in ADR-0007). No team, no auth,
no multi-tenancy. Reliability bar: personal-tool grade, but silence must be
distinguishable from calm — a degraded feed shows as a banner on the page
([ADR-0010](docs/adr/0010-feed-health-staleness-alerts.md)).

## Mental model of the feeds

The three feeds are **pipeline layers, not redundant sources**:

| Layer | Feed | Latency | Provides |
|---|---|---|---|
| Sensor detection | USGS | minutes | EQ only; physical severity; mutable (revised, re-keyed, deleted) |
| Modeled impact | GDACS | ~25 min for EQ (waits on ShakeMap) | Green/Orange/Red = exposure × vulnerability, all hazard types |
| Editorial confirmation | ReliefWeb | hours–days, no SLA | Human-written reports; GLIDE numbers; attention ≠ severity |

Consequences: a poller with per-feed cadence; an event store that treats
events as *mutable claims* keyed by source ID; explicit re-notification
policy; raw payload archive for audit/replay.

## What it does (decided)

- **Trigger** on humanitarian impact: GDACS Orange/Red (episode level)
  primary; USGS PAGER yellow+ secondary; fast provisional path for USGS
  M≥6.0 near populated land (labeled unassessed, upgraded/dropped when
  GDACS/PAGER arrive); ReliefWeb never triggers — enrichment only.
  [ADR-0001](docs/adr/0001-impact-based-trigger-policy.md)
- **Scope**: global; alert on earthquakes, tropical cyclones, floods;
  volcanoes/droughts store-but-don't-alert; wildfires only at Red (they are
  ~81% of GDACS RSS volume).
  [ADR-0002](docs/adr/0002-hazard-scope.md)
- **Updates**: re-notify on escalation, provisional-confirmation, and
  retraction; silently store downgrades and minor revisions. Follow-up
  notifications per event are coalesced (max ~1 per 30 min); genuinely new
  events always alert immediately.
  [ADR-0003](docs/adr/0003-update-and-renotification-semantics.md)
- **Dedup**: one canonical event per real-world disaster with per-source
  claims underneath; GLIDE match first, fuzzy fallback (hazard + country +
  ±48 h + geometry); conservative — a false merge is worse than a missed one.
  [ADR-0004](docs/adr/0004-dedup-canonical-events.md)
- **Polling**: USGS summary feed 60 s (If-Modified-Since); GDACS RSS 6 min
  (ETag); ReliefWeb 30 min consolidated (~96 of the 1,000 daily call cap).
  [ADR-0005](docs/adr/0005-polling-cadence.md)
- **Persistence**: SQLite (`events`, `source_records`, `notifications`) +
  raw payload archive on disk, written before parsing; keep everything
  indefinitely (KB-scale volumes; the archive is the replay-test corpus).
  [ADR-0006](docs/adr/0006-persistence-sqlite-raw-archive.md)
- **Cold start**: backfill recent history (USGS FDSN + GDACS 7-day feed)
  store-only, but alert events still at Orange/Red — ongoing crises matter.
  [ADR-0009](docs/adr/0009-cold-start-backfill.md)
- **Feed health**: if a feed hasn't succeeded within N× its cadence, one
  "degraded" notice + one recovery notice; exponential backoff on 429/5xx.
  [ADR-0010](docs/adr/0010-feed-health-staleness-alerts.md)
- **ReliefWeb** sits behind a feature flag until the pre-approved `appname`
  arrives; GDACS+USGS don't wait for it.
  [ADR-0011](docs/adr/0011-reliefweb-feature-flag.md)

## How it's built (decided)

- **Python**, long-running process on an **always-on VPS/home server**
  (systemd service). [ADR-0008](docs/adr/0008-python-on-always-on-server.md)
- **MVP sequencing**: thin vertical slice — USGS-only end-to-end
  (poll → store → trigger → web page) with the dedup-ready schema from day
  one; then GDACS; then ReliefWeb.
  [ADR-0012](docs/adr/0012-vertical-slice-and-replay-testing.md)
- **Testing**: replay recorded real payloads (including BOM-prefixed XML,
  re-keyed USGS events, in-place GDACS guid updates, deletions) through the
  pipeline. Same ADR-0012.
- **Delivery**: a pull-based web page (`hadr web`, stdlib server on
  localhost) showing a feed-health banner, current active alerts, and a recent
  updates feed — read live from SQLite. Each update keeps the compact content
  (hazard, level, magnitude/name, country, event link).
  [ADR-0013](docs/adr/0013-web-app-pull-delivery.md)

## Hard constraints (external, non-negotiable)

- ReliefWeb: v2 API only (v1 returns 410); pre-approved `appname` required
  since 2025-11-01 (403 without); **1,000 calls/day hard cap**.
- USGS: events are mutable — revised, re-keyed (preferred ID changes),
  deleted; unpublished 429 threshold; responses cached 60 s server-side.
- GDACS: RSS guid updates in place (track `eventid` + `episodeid`);
  `alertlevel` (lifetime max) ≠ `episodealertlevel` (current); UTF-8 BOM;
  georss is lat-lon but the GeoJSON API is lon-lat; no status page.
- GLIDE is the intended cross-feed key but is often empty early on GDACS —
  dedup cannot rely on it alone.

## Blocking action items (user-side)

- [ ] Request ReliefWeb `appname` at
      https://apidoc.reliefweb.int/parameters#appname (human approval;
      everything else proceeds meanwhile).
- [ ] Provision the always-on host to run `hadr run` (poller) and `hadr web`
      (page). No delivery secrets needed since the switch to the web app
      (ADR-0013).

## Tunables deliberately left as config, not decisions

Per-event coalescing window (default 30 min), backfill window (default
72 h), staleness multiplier N (default 3×), M≥6.0 provisional threshold.
Tune with real traffic after the MVP runs.
