# CLAUDE.md

Product context lives in `CONTEXT.md`; decisions in `docs/adr/`; open
questions in `QUESTIONS.md`. Read those before proposing design changes.

## Language & tooling

- **Python 3.11+**, managed with **`uv`**. Deps in `pyproject.toml`; run
  commands via `uv run …` (creates/uses `.venv` automatically).
- HTTP: `httpx`. Persistence: stdlib `sqlite3`. No ORM.
- Delivery is a pull-based web page served by the stdlib `http.server`
  (`hadr web`) — no web framework (ADR-0013).

## Test command

    uv run pytest            # full suite
    ./scripts/check.sh       # deterministic gate: ruff + pytest

## Conventions

1. **Store raw before parsing.** Every fetched payload is archived verbatim
   to disk before it is parsed (ADR-0006). Parsers read from the archive in
   tests (ADR-0012 replay fixtures).
2. **Events are mutable claims.** Never overwrite a source's data with
   another source's; each source's claim lives in `source_records` under a
   canonical event (ADR-0004). Trigger/notify logic reads canonical events,
   never raw feed items.
3. **Config, not constants.** Tunables (thresholds, cadences, windows) come
   from env via `hadr/config.py`; secrets from `.env` (gitignored). No
   magic numbers inline.
4. **Silence must be trustworthy.** A failure that stops alerts must surface
   (feed-health notice, ADR-0010) — never fail silent.

## Deviations policy

Anything built that departs from `CONTEXT.md`, an ADR, or this file is
recorded in `implementation-notes.md` under **Deviations**, with the reason.
An undocumented deviation is a bug.
