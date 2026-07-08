#!/usr/bin/env bash
# Deterministic gate (scripts/README.md): same answer twice, no prompts.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== ruff =="
uv run ruff check hadr tests

echo "== pytest =="
uv run pytest -q
