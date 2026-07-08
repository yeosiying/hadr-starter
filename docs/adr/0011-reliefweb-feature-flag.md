# ADR-0011: ReliefWeb behind a feature flag; build doesn't wait for appname

Date: 2026-07-08 · Status: Accepted

## Context

Since 2025-11-01 every ReliefWeb API request requires a pre-approved
`appname` (403 otherwise), granted through a human approval process of
unknown duration — and the request hasn't been submitted yet. ReliefWeb
never triggers alerts (ADR-0001); it only enriches and confirms. Blocking
the whole build on an external approval would be pure waste.

## Decision

- MVP builds and ships on **GDACS + USGS only**.
- All ReliefWeb code sits behind a **config flag** (off by default, plus the
  `appname` value itself as config); turning it on later requires no schema
  or pipeline changes — the `source_records` layer treats it as just another
  source.
- **Request the appname now, in parallel** (user-side action item in
  CONTEXT.md): https://apidoc.reliefweb.int/parameters#appname
- When enabled: 30 min consolidated polling (ADR-0005), `date.created` for
  incremental sync, explicit `sort`, POST JSON filters, `disasters` status
  filtered for both `current` and `ongoing`.

## Consequences

- Time-to-first-alert doesn't depend on a third party.
- Until the flag is on, events lack editorial confirmation and ReliefWeb
  GLIDE cross-references — dedup runs on GDACS GLIDE + fuzzy matching alone,
  which it must support anyway (ADR-0004).
- Dropping ReliefWeb permanently was rejected: GLIDE cross-referencing and
  human confirmation are worth the wait.
