# ADR-0010: Feed staleness alerts — silence must be distinguishable from calm

Date: 2026-07-08 · Status: Accepted

## Context

GDACS has unannounced downtime and no status page; USGS rate-limits (429) at
an unpublished threshold; ReliefWeb has no SLA. For an alerting tool, the
worst failure mode is *silent*: a dead feed looks identical to a quiet world,
and the user only finds out during the next disaster.

## Decision

- Track last-successful-fetch per feed. If a feed hasn't succeeded within
  **N× its cadence** (default N=3, config), surface it as **degraded**. Under
  push delivery (original ADR-0007) that was one degraded + one recovery
  notice; under the web app (ADR-0013) it is a **health banner** on the page
  computed from `feed_state`. Either way, degradation is visible, not silent.
- **Exponential backoff with jitter** on 429/5xx (respecting `Retry-After`
  when present), overriding the normal cadence; conditional requests
  (ETag / If-Modified-Since) always, to stay polite.
- Feed-health notices are operational messages, exempt from the per-event
  coalescing of ADR-0003 but capped at one degraded+one recovery per outage.

## Consequences

- The user can trust silence: no alerts + no degraded notice = genuinely calm.
- Health state lives in the store, surviving restarts (a reboot during a
  GDACS outage shouldn't re-announce it).
- Backoff interacts with staleness: a long 429 backoff on USGS will
  legitimately trip the staleness alert — that's correct behavior, the feed
  *is* degraded for our purposes.
