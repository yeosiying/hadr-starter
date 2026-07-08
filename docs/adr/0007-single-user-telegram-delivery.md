# ADR-0007: Single-user Telegram delivery, compact alert format

Date: 2026-07-08 · Status: **Superseded by [ADR-0013](0013-web-app-pull-delivery.md)**

> Superseded 2026-07-08: the owner switched from Telegram push to a pull-based
> web app. The audience (just me) and the compact message content are
> unchanged and carried forward; only the delivery channel changed. The
> internal `notify()` seam this ADR introduced is what made the swap cheap.

## Context

The product's whole point is not watching websites, so delivery must push.
The audience decision (QUESTIONS.md Q1) is **just me** — one recipient, no
team, no auth. Candidates: Telegram, Slack, email, dashboard.

## Decision

- **Telegram bot** is the sole MVP delivery channel: pushes to phone, free,
  and sending is a single HTTPS POST (`sendMessage`) — no library needed.
- **Compact alert format**, one message per notification:
  hazard type (with emoji), alert level (GDACS color / PAGER color /
  "UNASSESSED" for the provisional path), magnitude or storm name, country,
  exposed-population estimate when available, links to the GDACS and USGS
  event pages. Update/retraction messages reference the original alert.
- Delivery goes through one internal `notify()` seam so a second channel
  could be added later, but no pluggable-channel framework is built now —
  single-user was chosen explicitly over "team-ready later".

## Consequences

- Needs a bot token (@BotFather) and chat ID as config/secrets — user-side
  setup item in CONTEXT.md.
- Telegram API outages are a single point of failure for delivery; failed
  sends are recorded in `notifications` and retried with backoff.
- Rich content (maps, severity history) is deliberately out; the event store
  has the data if a digest/dashboard is wanted later.
