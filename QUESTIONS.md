# QUESTIONS — HADR Monitoring Agent

Questions asked while turning REQS.md into CONTEXT.md + ADRs.
Status: `OPEN` / `ANSWERED (→ ADR)` / `DEFERRED`.
All 12 answered 2026-07-08.

---

## Round 1 — Foundational

### Q1. Who consumes the alerts? `ANSWERED → ADR-0007`
**Answer: A — Just me.** Single recipient, no auth/multi-user. One internal
`notify()` seam is kept, but no pluggable-channel framework ("team-ready
later" was explicitly declined).
- ~~B. Me now, small team later~~ (recommended, declined)
- ~~C. Team/ops center from day one~~

### Q2. Alert delivery channel for MVP? `REVISED 2026-07-08 → ADR-0013`
**Original answer: A — Telegram bot** (→ ADR-0007). **Revised: a pull-based
web app** the owner visits (`hadr web`, localhost). Audience unchanged (still
just me, Q1); only push→pull changed. See
[ADR-0013](docs/adr/0013-web-app-pull-delivery.md), which supersedes ADR-0007.
- ~~A. Telegram bot~~ (original, revised away) · ~~B. Email~~ · ~~C. Slack~~
- ~~D. Terminal/dashboard~~ → effectively chosen: a local web dashboard.

### Q3. Deployment target? `ANSWERED → ADR-0008`
**Answer: A — Always-on VPS/home server**, systemd service.
- ~~B. Laptop process~~ (silent gaps) · ~~C. Serverless/cron~~ (fights 60 s cadence + SQLite)

### Q4. Implementation language? `ANSWERED → ADR-0008`
**Answer: A — Python.** feedparser/httpx/sqlite3; fastest iteration on
parsing quirks, which is where the real work is.
- ~~B. TypeScript/Node~~ · ~~C. Go~~

## Round 2 — Operational semantics

### Q5. Alert-storm / fatigue policy? `ANSWERED → ADR-0003`
**Answer: A — Per-event throttle.** New events alert immediately; follow-ups
per event coalesced to ~1 per 30 min (config); retractions jump the queue.
- ~~B. Global rate cap + digest~~ · ~~C. No throttling for MVP~~

### Q6. Cold-start / backfill behavior? `ANSWERED → ADR-0009`
**Answer: C — Backfill (72 h default, store-only) and alert events still at
Orange/Red.** Ongoing crises survive reboots.
- ~~A. Backfill store-only~~ · ~~B. Start from now~~

### Q7. Feed-outage / staleness handling? `ANSWERED → ADR-0010`
**Answer: A — Self-monitor with staleness alert.** One degraded + one
recovery notice at N×cadence (N=3 default); backoff on 429/5xx. Silence must
be distinguishable from calm.
- ~~B. Silent retry + log only~~

### Q8. ReliefWeb appname pending — MVP handling? `ANSWERED → ADR-0011; REFINED → ADR-0014`
**Answer: A — Feature flag, don't block.** GDACS+USGS MVP; request appname in
parallel (still a user-side TODO). **Refined 2026-07-08 (ADR-0014):** the
public RSS feed needs no approval and carries GLIDE, so ReliefWeb enrichment
shipped now via RSS (enabled by default); the appname-gated JSON API is a
later upgrade rather than a blocker.
- ~~B. Wait for appname~~ · ~~C. Drop ReliefWeb~~

## Round 3 — Scope & quality bar

### Q9. MVP sequencing? `ANSWERED → ADR-0012`
**Answer: A — Thin vertical slice.** USGS end-to-end first (with dedup-ready
schema from day one), then GDACS + full trigger policy, then ReliefWeb.
- ~~B. Store-only first~~ · ~~C. Full scope at once~~

### Q10. What goes in an alert message? `ANSWERED → ADR-0007`
**Answer: A — Compact + links.** Hazard, level, magnitude/name, country,
exposed population, GDACS/USGS links; updates reference the original.
- ~~B. Rich digest~~ · ~~C. Minimal~~

### Q11. Raw payload & event retention? `ANSWERED → ADR-0006`
**Answer: A — Keep everything indefinitely.** KB-scale volumes; the raw
archive is the audit trail and replay-test corpus.
- ~~B. Prune raw after N days~~

### Q12. Testing approach? `ANSWERED → ADR-0012`
**Answer: A — Replay fixtures.** Record real payloads (incl. BOM, re-keyed
USGS events, deletions, in-place GDACS guid updates) and replay through the
pipeline. Live smoke test manual-only, never CI-gating.
- ~~B. Parser unit tests only~~ · ~~C. Live smoke tests~~

---

## Decisions imported from REQS.md (recorded, not re-asked)

| Decision | ADR |
|---|---|
| Impact-based trigger policy (GDACS Orange+ / PAGER yellow+ / M≥6.0 provisional / ReliefWeb never) | [ADR-0001](docs/adr/0001-impact-based-trigger-policy.md) |
| Hazard scope (EQ/TC/FL alert; VO/DR store-only; WF at Red) | [ADR-0002](docs/adr/0002-hazard-scope.md) |
| Re-notification semantics (escalation/confirmation/retraction) | [ADR-0003](docs/adr/0003-update-and-renotification-semantics.md) |
| Canonical-event dedup, GLIDE-first, conservative | [ADR-0004](docs/adr/0004-dedup-canonical-events.md) |
| Polling cadences (USGS 60 s / GDACS 6 min / ReliefWeb 30 min) | [ADR-0005](docs/adr/0005-polling-cadence.md) |
| SQLite + raw payload archive | [ADR-0006](docs/adr/0006-persistence-sqlite-raw-archive.md) |

## Still open (not blocking design — tune with real data)

- Exact coalescing window, backfill window, staleness multiplier, M≥6.0
  threshold — all config, defaults set in ADRs.
- Fuzzy-dedup geometry distance threshold — tune via replay fixtures once
  real multi-source events are archived.
