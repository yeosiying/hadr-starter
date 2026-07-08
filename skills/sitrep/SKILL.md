---
name: sitrep
description: >
  Produce a concise HADR situation report from the current event store —
  active alerts by severity, notable changes, and feed health. Use when the
  user asks for a "sitrep", "situation report", "what's happening", or the
  morning brief. Reads local SQLite; makes no external calls and never
  fabricates events beyond what the feeds assert.
---

# HADR situation report

Turn the current store state into a short, trustworthy brief a human can read
in under a minute. This is the human-readable companion to the always-on web
page and the 08:30 `dashboard.html` snapshot.

## Steps

1. **Pull the data (deterministic — no model).** Run:

       uv run python skills/sitrep/query.py

   It prints JSON: `generated_at`, `feeds` (per-feed health), `active_alerts`
   (severity + hazard + title + country + reliefweb links), `recent_updates`
   (last 25 transitions). If it errors because the DB is empty, say so plainly
   — an empty store is a valid "all quiet" result, not a failure.

2. **Compose the report (prose — use a strong model, e.g. Opus/Sonnet).**
   Write Markdown following the template below. Rules:
   - Lead with feed health. If any feed is degraded, that line goes **first
     and bold** — silence must be trustworthy (ADR-0010). If all healthy, one
     quiet line.
   - Order active alerts by severity (RED → ORANGE → YELLOW → UNASSESSED).
     Flag `provisional: true` items explicitly as *unassessed*.
   - Summarize `recent_updates` as "what changed" — group escalations,
     confirmations, and stand-downs; don't dump every row.
   - No speculation, no severity claims the feeds didn't make, no physical
     magnitude presented as impact (see `goal.md` non-goals).
   - Keep it terse. If nothing is active, say "No active humanitarian alerts"
     and stop — do not pad.

3. **Save it (deterministic).** Write to `reports/sitrep-<UTC-date>.md`
   (`reports/` is gitignored). Print the path. Offer to share it if asked.

## Output template

```
# HADR Situation Report — <YYYY-MM-DD HH:MM UTC>

Feeds: <all healthy | ⚠ DEGRADED: <feeds>>

## Active alerts (<n>)
- <emoji> **<LEVEL>** <HAZARD> — <title>, <country>  <(unassessed) if provisional>
  <ReliefWeb: confirmed — link, if present>

## What changed (last 24h)
- <grouped escalations / confirmations / stand-downs, or "No changes.">

<one-sentence plain-language summary>
```

## Notes

- Step 1 and step 3 are deterministic and belong in scripts, not a prompt
  (they must give the same answer twice). Only step 2 needs a model.
- The routine at 08:30 Asia/Singapore regenerates `dashboard.html`
  (`hadr dashboard`); this skill is the on-demand, narrated version.
