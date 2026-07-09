# ADR-0006: SQLite event store + keep-everything raw payload archive

Date: 2026-07-08 · Status: Accepted

## Context

The store must handle mutable claims (updates, re-keys, deletions), power
dedup across sources, and record what was notified. Volumes are tiny —
KB-scale payloads, at most a few thousand events/year in scope. Single user,
single host (ADR-0008), no concurrent writers.

## Decision

- **SQLite**, three core tables:
  - `events` — canonical events (ADR-0004) with current trigger state;
  - `source_records` — per-source claims keyed by (source, source ID), with
    update history and ID aliases;
  - `notifications` — every message sent, with event, transition type, and
    timestamp (drives coalescing, ADR-0003).
- **Raw payload archive on disk**: every fetched payload written verbatim
  *before parsing*, organized by feed/date.
- **Retention: keep everything indefinitely** — raw archive included. It is
  the audit trail ("why did/didn't this alert?") and the replay-test corpus
  (ADR-0012). Revisit only if disk becomes a real constraint.

## Consequences

- No DB server to run; backup is copying files.
- Parser bugs are recoverable: fix the parser, replay the archive.
- If a team/ops-center ever materializes (rejected for now, see QUESTIONS.md
  Q1), SQLite's single-writer model is the first thing to revisit.
