# REQS - HADR Monitoring Agent (initial idea)

<!-- DRAFT by Claude from 2026-07-07/08 discussions. This file is meant to be
     YOUR handwritten capture of thoughts - edit/rewrite before running
     /build-plan-product. -->

## Idea

An agent that monitors global disaster feeds (GDACS, USGS, ReliefWeb) and
alerts on humanitarian-relevant events, so a HADR-interested user doesn't have
to watch three websites.

## What it should do

- Poll the three feeds continuously (nothing pushes; per-feed cadence:
  USGS 60s, GDACS 6min, ReliefWeb 30min within its 1,000 calls/day cap).
- Trigger alerts on humanitarian impact, not physical severity:
  - GDACS Orange/Red (episode alert level) - primary
  - USGS PAGER yellow+ - secondary
  - Fast provisional path: USGS M>=6.0 near populated land, labeled
    unassessed, upgraded/dropped when GDACS/PAGER arrive
  - ReliefWeb never triggers - enrichment/confirmation only
- Scope: global; alert on earthquakes, tropical cyclones, floods;
  store-but-don't-alert volcanoes and droughts; wildfires only at Red.
- Re-notify on escalation, provisional confirmation, and retraction;
  silently store downgrades and minor revisions.
- Deduplicate across sources into one canonical event per real-world
  disaster (GLIDE match first, fuzzy fallback: hazard + country + time
  window + geometry). Conservative merging.
- Persist: SQLite event store (events, source_records, notifications) plus
  raw payload archive on disk.

## Known constraints

- ReliefWeb requires pre-approved appname (request pending/todo); 1,000
  calls/day hard cap; v2 API only.
- USGS events are mutable: revised, re-keyed, deleted. Event store must
  handle updates and retractions.
- GDACS RSS guid updates in place; track eventid + episodeid.

## Open / undecided

- Alert delivery channel (terminal? email? Slack/Telegram? dashboard?)
- Who is the user of the alerts (just me? a team? ops center?)
- Deployment target (laptop process? server? cloud cron?)
- Language/framework for implementation
