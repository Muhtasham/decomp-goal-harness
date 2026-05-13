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
uv run --project "$ROOT" decomp-goal targets --repo "$ROOT/examples/toy_match" --rank --json >/dev/null
uv run --project "$ROOT" decomp-goal run --repo "$ROOT/examples/toy_match" --unit attempt.c --state-dir "$STATE_DIR" --json >/dev/null

if uv run --project "$ROOT" decomp-goal run --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --json >/dev/null; then
  echo "expected attempt.start.c to be non-matching" >&2
  exit 1
fi

uv run --project "$ROOT" decomp-goal history --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal checkpoint --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal coach --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal lead --repo "$ROOT/examples/toy_match" --unit attempt.start.c --json >/dev/null
uv run --project "$ROOT" decomp-goal lead --repo "$ROOT/examples/toy_match" --unit attempt.start.c --diff-json "$ROOT/examples/toy_match/sample_objdiff.json" --diff-format objdiff --json >/dev/null
uv run --project "$ROOT" decomp-goal experiments --repo "$ROOT/examples/toy_match" --unit attempt.start.c --out "$STATE_DIR/experiments.md" --json >/dev/null
test -s "$STATE_DIR/experiments.md"
VARIANT_STATE="$STATE_DIR/variants"
mkdir -p "$VARIANT_STATE"
uv run --project "$ROOT" decomp-goal run --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$VARIANT_STATE" --json >/dev/null || true
uv run --project "$ROOT" decomp-goal variants --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$VARIANT_STATE" --patch-dir "$ROOT/examples/toy_match/variants" --allow-dirty --json >/dev/null
uv run --project "$ROOT" decomp-goal steer --repo "$ROOT/examples/toy_match" --unit attempt.start.c --source smoke --text "branch condition lead" --json >/dev/null
uv run --project "$ROOT" decomp-goal steer --repo "$ROOT/examples/toy_match" --json >/dev/null
uv run --project "$ROOT" decomp-goal decompilers --repo "$ROOT/examples/toy_match" --unit attempt.start.c --function score_room --source ghidra --file "$ROOT/examples/toy_match/decompiler-ghidra.txt" --notes "branch and constant shape agree" --confidence high --json >/dev/null
uv run --project "$ROOT" decomp-goal decompilers --repo "$ROOT/examples/toy_match" --unit attempt.start.c --json >/dev/null
uv run --project "$ROOT" decomp-goal gaps --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal monitor --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --dashboard-out "$STATE_DIR/monitor.html" --max-ticks 1 --json >/dev/null
test -s "$STATE_DIR/monitor.html"
uv run --project "$ROOT" decomp-goal codex --repo "$ROOT/examples/toy_match" --unit attempt.c --mode exec --reasoning-effort high --json >/dev/null
uv run --project "$ROOT" decomp-goal dashboard --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --out "$STATE_DIR/dashboard.html" >/dev/null
test -s "$STATE_DIR/dashboard.html"

echo "smoke ok"
