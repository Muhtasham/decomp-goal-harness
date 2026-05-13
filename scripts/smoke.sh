#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$(mktemp -d)"
trap 'rm -rf "$STATE_DIR"' EXIT

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required" >&2
  exit 1
fi

uv run --project "$ROOT" python -m compileall "$ROOT/src" "$ROOT/examples/toy_match/score.py" >/dev/null
uv run --project "$ROOT" decomp-goal inspect --repo "$ROOT/examples/toy_match" --json >/dev/null
uv run --project "$ROOT" decomp-goal run --repo "$ROOT/examples/toy_match" --unit attempt.c --state-dir "$STATE_DIR" --json >/dev/null

if uv run --project "$ROOT" decomp-goal run --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --json >/dev/null; then
  echo "expected attempt.start.c to be non-matching" >&2
  exit 1
fi

uv run --project "$ROOT" decomp-goal history --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal coach --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal lead --repo "$ROOT/examples/toy_match" --unit attempt.start.c --json >/dev/null
uv run --project "$ROOT" decomp-goal experiments --repo "$ROOT/examples/toy_match" --unit attempt.start.c --out "$STATE_DIR/experiments.md" --json >/dev/null
test -s "$STATE_DIR/experiments.md"
uv run --project "$ROOT" decomp-goal dashboard --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --out "$STATE_DIR/dashboard.html" >/dev/null
test -s "$STATE_DIR/dashboard.html"

echo "smoke ok"
