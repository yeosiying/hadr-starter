# ADR-0008: Python long-running service on an always-on host

Date: 2026-07-08 · Status: Accepted

## Context

A 60 s USGS cadence and stateful dedup imply a long-running process, not
cron/serverless: serverless makes SQLite awkward (persistent volume) and
sub-minute schedules expensive; a laptop process leaves silent coverage gaps
when it sleeps. Language candidates: Python, TypeScript/Node, Go.

## Decision

- **Python** — best ecosystem fit for this exact job: `feedparser` for RSS
  quirks (BOM tolerance), `httpx` for conditional requests, `sqlite3` in the
  stdlib; fastest iteration on parsing edge cases, which is where the real
  work is.
- Runs as a **single long-lived process on an always-on VPS or home
  server**, managed by **systemd** (restart-on-failure, journald logs).
- Async scheduling (`asyncio`) for the per-feed cadences in one process; no
  worker queues, no containers-orchestration — one box, one service.

## Consequences

- Host provisioning is a user-side setup item (CONTEXT.md).
- Crash-restart via systemd plus cold-start backfill (ADR-0009) means
  downtime degrades to "late alerts", not lost events.
- Go's single-binary deploy is given up; acceptable for a personal tool on a
  box we control.
