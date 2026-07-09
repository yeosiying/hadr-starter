# ADR-0005: Per-feed polling cadence within provider limits

Date: 2026-07-08 · Status: Accepted

## Context

Nothing pushes; all three feeds must be polled. Providers differ sharply:
USGS regenerates summary feeds every minute and server-caches responses 60 s;
GDACS RSS regenerates ~every 6 min and supports ETag/Last-Modified; ReliefWeb
has a hard 1,000 calls/day cap (≈1 call per 90 s total budget) and no SLA on
editorial latency anyway.

## Decision

| Feed | Cadence | Conditional mechanism | Notes |
|---|---|---|---|
| USGS summary GeoJSON | 60 s | If-Modified-Since (no usable ETag) | Re-fetch event detail only when `updated` changed |
| GDACS RSS | 6 min | ETag / Last-Modified | Matches regeneration interval |
| ReliefWeb | 30 min | n/a | Consolidated POST queries; ~96 calls/day of the 1,000 cap |

Exponential backoff on 429/5xx overrides cadence (see ADR-0010).

## Consequences

- ReliefWeb's ≤10% budget use leaves headroom for backfill queries and
  occasional manual investigation.
- Faster polling of USGS is pointless (server cache) and of GDACS wasteful
  (regeneration interval) — cadences are ceilings by design, kept as config.
- 60 s cadence implies a long-running process, feeding ADR-0008.
