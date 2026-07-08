# ADR-0013: Pull-based web app delivery (supersedes ADR-0007)

Date: 2026-07-08 · Status: Accepted (supersedes [ADR-0007](0007-single-user-telegram-delivery.md))

## Context

ADR-0007 chose Telegram push to a single user. The owner has since changed the
delivery preference: rather than receiving pushes, they want to **visit a web
page** to see the current state on demand. Audience is unchanged — still just
the owner (QUESTIONS.md Q1); only the delivery style flips from push to pull.

This also aligns with the course end-state in `README.md` (a `dashboard.html`
product), and reuses the internal `notify()` seam ADR-0007 kept for exactly
this kind of swap.

## Decision

- **Delivery is pull.** Recording a notification *is* the delivery: the
  pipeline still computes transitions (NEW / ESCALATION / CONFIRMATION /
  RETRACTION per ADR-0003) and writes `notifications` rows. There is no push
  channel; Telegram is removed.
- **A `hadr web` command** runs a stdlib `http.server` (no framework,
  CLAUDE.md tooling) that queries the SQLite store on each request and renders
  one self-contained HTML page:
  - a **feed-health banner** (ADR-0010) computed from `feed_state`;
  - **current active alerts** (`events` at an alertable level, not retracted);
  - a **recent updates feed** (the `notifications` rows).
- **Decoupled process.** The poller (`hadr run`) writes; the web server reads
  the same SQLite file in a separate process. SQLite handles concurrent readers.
- **Localhost, no auth** (QUESTIONS.md Q2 revised). Binds `127.0.0.1:8000` by
  default (`HADR_WEB_HOST` / `HADR_WEB_PORT`).
- Per-event coalescing (ADR-0003) is retained — it keeps the updates feed
  readable rather than throttling a push.

## Consequences

- No delivery secrets: `.env` no longer needs a bot token/chat id.
- "Silence must be trustworthy" (CLAUDE.md convention 4, ADR-0010) is now a
  **visible banner** instead of a push — a degraded feed shows on the page.
- The page auto-refreshes (30 s) so a left-open tab stays current; there is no
  proactive notification, which is the accepted trade-off of pull delivery.
- The `notify()` seam remains: a future push channel could be re-added
  alongside the web view without touching the pipeline.
- Exposing beyond localhost (LAN/public) would need hardening (rejected for now).
