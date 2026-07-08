# ADR-0014: ReliefWeb enrichment via public RSS now; JSON API as a later upgrade

Date: 2026-07-08 · Status: Accepted (refines [ADR-0011](0011-reliefweb-feature-flag.md))

## Context

ADR-0011 put all of ReliefWeb behind a feature flag on the assumption that the
whole feed was blocked on a pre-approved `appname` (the JSON API returns 403
without it, and approval is a slow human process). Reading `feeds/reliefweb.md`
surfaced a second door: the **public RSS feed**
(`https://reliefweb.int/disasters/rss.xml`) needs **no approval** and already
carries the one field enrichment most needs — the **GLIDE** number — plus the
disaster title, link, country, and date.

So ReliefWeb enrichment is not actually blocked. Only the *richer, structured*
API path is.

## Decision

- **Ship ReliefWeb enrichment now, sourced from the RSS feed**, enabled by
  default (`HADR_RELIEFWEB_ENABLED=true`). No secrets required.
- **The appname-gated JSON API is a documented upgrade**, not a prerequisite.
  `HADR_RELIEFWEB_APPNAME` is reserved; when it is set (after approval), a
  future change swaps the RSS backend for the API to gain structured status
  lifecycle, `related_glide`, reliable `date.created` sync, and query filters.
- **Everything else from ADR-0011 stands**: ReliefWeb never triggers alerts
  (ADR-0001) — every record's `claim_level` is NONE; it is just another source
  under a canonical event (ADR-0004).
- **Enrich-only ingestion**: a ReliefWeb record attaches to an *existing*
  canonical event (GLIDE first — matched hazard-agnostically since GLIDE is
  globally unique — then fuzzy geometry) or is skipped. It never creates a
  standalone event, so an editorial disaster with no GDACS/USGS counterpart is
  archived but adds nothing to the alertable store.

## Consequences

- The three-feed picture is complete today, without waiting on approval.
- RSS is coarser than the API: no status lifecycle (records are marked
  `current`), country-level (no coordinates, so cross-feed joins lean on
  GLIDE), hazard is inferred from the GLIDE prefix / title (best-effort, and
  only cosmetic since matching is GLIDE-based and standalone events are
  skipped).
- The upgrade is isolated to `hadr/feeds/reliefweb.py` + config; the pipeline,
  dedup, and web layers are source-agnostic and unaffected.
- Still worth requesting the appname (ADR-0011 action item) for the richer
  data — now an enhancement, no longer a blocker.
