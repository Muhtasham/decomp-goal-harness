#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/src"

python3 -m compileall "$ROOT/src" "$ROOT/examples/toy_match/score.py" >/dev/null
python3 -m decomp_goal inspect --repo "$ROOT/examples/toy_match" --json >/dev/null
python3 -m decomp_goal run --repo "$ROOT/examples/toy_match" --unit attempt.c --json >/dev/null

if python3 -m decomp_goal run --repo "$ROOT/examples/toy_match" --unit attempt.start.c --json >/dev/null; then
  echo "expected attempt.start.c to be non-matching" >&2
  exit 1
fi

echo "smoke ok"
