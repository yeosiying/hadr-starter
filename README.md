# HADR Monitor

A monitoring agent for humanitarian assistance and disaster response (HADR).

## The end state

By Wednesday this repository contains an agent that watches live disaster feeds
(GDACS, USGS, ReliefWeb — see `feeds/`), filters the noise, assesses what remains, and
publishes a morning situation report to `dashboard.html` at 08:30 Singapore time — on a
schedule, unattended, quiet when nothing has changed. How it does that is the course.

## The three days

1. **Plan** — interrogate the feeds, write the PRD, cut it into vertical slices
2. **Autonomy** — build a slice, write a skill, wire up the 08:30 routine, launch the overnight loop
3. **Trust** — review code you didn't write, harden the pipeline, demo

## Artefacts expected

`prd.html` · `system-view.html` · `implementation-notes.md` · `dashboard.html` · `goal.md` · at least one skill

## Day 1 setup

1. Sign in to Claude Code with your Team seat
2. Create your own repository from this template, then clone it
3. Run `/install-github-app` so @claude reviews your pull requests from Day 2
4. Install OpenCode and sign in with your Go key

Fill in `CLAUDE.md` before your first prompt.
