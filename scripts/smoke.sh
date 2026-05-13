#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/src"
STATE_DIR="$(mktemp -d)"
trap 'rm -rf "$STATE_DIR"' EXIT

python3 -m compileall "$ROOT/src" "$ROOT/examples/toy_match/score.py" >/dev/null
python3 -m decomp_goal inspect --repo "$ROOT/examples/toy_match" --json >/dev/null
python3 -m decomp_goal run --repo "$ROOT/examples/toy_match" --unit attempt.c --state-dir "$STATE_DIR" --json >/dev/null

if python3 -m decomp_goal run --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --json >/dev/null; then
  echo "expected attempt.start.c to be non-matching" >&2
  exit 1
fi

python3 -m decomp_goal history --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
python3 -m decomp_goal dashboard --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --out "$STATE_DIR/dashboard.html" >/dev/null
test -s "$STATE_DIR/dashboard.html"

echo "smoke ok"
