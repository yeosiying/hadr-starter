# HADR Monitor

A monitoring agent for humanitarian assistance and disaster response (HADR).

## The end state

By Wednesday afternoon this repository contains an agent that:

- watches live disaster feeds — GDACS, USGS and ReliefWeb (see `feeds/`)
- filters out the noise and assesses what remains: what happened, where, how bad, who is affected
- publishes a morning situation report to `dashboard.html` at 08:30 Singapore time
- runs on a schedule, unattended, and stays quiet when nothing has changed

How it does any of that is not specified anywhere in this repository. That is the course.

## The three days

1. **Plan** — interrogate the feeds, write the PRD, cut it into vertical slices
2. **Autonomy** — build the first slice, write a skill, wire up the 08:30 routine, launch the overnight loop
3. **Trust** — review code you didn't write, harden the pipeline, demo

## Artefacts expected by the end

| Artefact | What it is |
| --- | --- |
| `prd.html` | The product requirements — what the agent must do, and why |
| `system-view.html` | How the pieces fit: feeds in, report out, what runs when |
| `implementation-notes.md` | The running log the agent keeps and you review (already stubbed) |
| `dashboard.html` | The product — the committed morning situation report |
| `goal.md` | The north star the overnight loop works towards |
| at least one skill | A reusable, model-aware procedure under `skills/` |

## Repository layout

```
.
├── CLAUDE.md               # Project conventions — fill this in before your first prompt
├── README.md               # This file
├── implementation-notes.md # The agent's working log; one entry per block, reviewed by you
├── feeds/                  # What each source is, its endpoint, and the open questions it raises
│   ├── gdacs.md            #   Multi-hazard, colour-coded alerts (EU/UN)
│   ├── usgs.md             #   Real-time earthquakes (US Geological Survey)
│   └── reliefweb.md        #   Curated humanitarian disasters (UN OCHA)
├── scripts/                # Deterministic checks — anything that must give the same answer twice
├── skills/                 # Skills you write on Day 2, one folder per skill
├── docs/
│   └── solutions/          # One learning per file; grepped before debugging
└── .github/
    ├── workflows/          # @claude review + the disabled morning sitrep
    └── ISSUE_TEMPLATE/     # Templates for vertical slices and skill feedback
```

`reports/` and `*.sitrep.html` are gitignored — the morning routine rebuilds them and their
churn does not belong in history. `dashboard.html` is the deliberate exception: it is the
product, and it is committed. Secrets live in `.env`, which stays out of the repo and out of the
agent's context.

## The three feeds

Each file in `feeds/` gives you the verified endpoint, a truncated example response, and a short
list of open questions. Those questions are the interesting part — they are where the design
decisions hide.

- **GDACS** (`feeds/gdacs.md`) — GeoJSON, multi-hazard, colour-coded alert levels. The same
  physical earthquake can also reach you through USGS, since both draw on NEIC.
- **USGS** (`feeds/usgs.md`) — GeoJSON earthquake feed, regenerated every minute as rolling
  windows. Events get revised — magnitude, location, occasionally deleted — after you have
  already seen them.
- **ReliefWeb** (`feeds/reliefweb.md`) — UN OCHA, curated and slower. The `v2` API now needs a
  **pre-approved** `appname` (requested via a form, confirmed by email); the RSS feed needs no
  approval but gives you less. Decide what you build against while approval is pending.

Recurring design tension across all three: **when are two records the same event?** Watch the
GLIDE numbers, shared identifiers, and overlapping geography.

## The morning routine

`.github/workflows/sitrep.yml.disabled` is the skeleton of the scheduled job. It is disabled on
purpose — a scheduled workflow that does nothing still costs minutes and trust. Rename it to
`sitrep.yml` only once its two TODO steps exist:

1. **A deterministic check** — a script in `scripts/` decides whether anything changed. It must
   not call a model.
2. **The report, only on change** — headless Claude (`claude -p`) runs your `/sitrep` skill and
   republishes `dashboard.html`, guarded on step 1.

The principle: the model never decides whether to wake up. A deterministic check does; the model
only runs when there is something to say.

Two other workflows are already live: `claude.yml` (mention @claude on an issue or PR) and
`claude-code-review.yml` (automatic review on pull requests) — both wired up by
`/install-github-app` on Day 1.

## Conventions to record

Fill in `CLAUDE.md` before your first prompt — at least three conventions. An empty conventions
file is also a decision, just not one you made. It covers:

- **Language & tooling** — what you build in
- **Test command** — how the agent checks its own work
- **Conventions** — the house style the agent must follow
- **Deviations policy** — what the agent does when the PRD and reality disagree

Anything built that departs from the PRD or `CLAUDE.md` gets recorded in
`implementation-notes.md` with the reason. An undocumented deviation is a bug.

When something costs you more than ten minutes to figure out, the fix goes in `docs/solutions/`
as one file (`YYYY-MM-DD-short-slug.md`, with frontmatter) so no future session pays for it
twice. See `docs/solutions/2026-07-06-example-follow-redirects.md` for the shape, and delete it
once you have a real one.

## Working with issues

Two issue templates keep the work legible:

- **Vertical slice** — one thin feature that runs end to end, with an observable definition of
  done and an explicit out-of-scope so nobody (human or agent) helpfully overreaches.
- **Skill issue** — filed against a neighbour's skill after you install and run it.

## Day 1 setup

1. Sign in to Claude Code with your Team seat
2. Create your own repository from this template, then clone it
3. Run `/install-github-app` so @claude reviews your pull requests from Day 2
4. Install OpenCode and sign in with your Go key

Fill in `CLAUDE.md` before your first prompt.
