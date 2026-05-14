#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$(mktemp -d)"
trap 'rm -rf "$STATE_DIR"' EXIT
LEADS_DIR="$STATE_DIR/leads"
DECOMPILER_DIR="$STATE_DIR/decompilers"
PROMPT_FILE="$STATE_DIR/goal.txt"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required" >&2
  exit 1
fi

if ! command -v cc >/dev/null 2>&1; then
  echo "cc is required for the toy matching oracle" >&2
  exit 1
fi

uv run --project "$ROOT" python -m compileall "$ROOT/src" "$ROOT/examples/toy_match/score.py" >/dev/null
uv run --project "$ROOT" decomp-goal inspect --repo "$ROOT" --json >/dev/null
uv run --project "$ROOT" decomp-goal doctor --repo "$ROOT" --json >/dev/null
uv run --project "$ROOT" decomp-goal gaps --repo "$ROOT" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal pick --repo "$ROOT" --json >/dev/null
uv run --project "$ROOT" decomp-goal run --repo "$ROOT" --unit attempt.c --state-dir "$STATE_DIR/root" --json >/dev/null
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
uv run --project "$ROOT" decomp-goal fuzz --repo "$ROOT/examples/toy_match" --unit attempt.c --state-dir "$STATE_DIR/fuzz" --patch "$ROOT/examples/toy_match/variants/worse-attempt.patch" --patch "$ROOT/examples/toy_match/variants/noop-comment.patch" --combo-size 2 --max-combos 1 --allow-dirty --json >/dev/null
git -C "$ROOT" diff --exit-code -- examples/toy_match/attempt.c >/dev/null
if uv run --project "$ROOT" decomp-goal variants --repo "$ROOT/examples/toy_match" --unit attempt.c --state-dir "$STATE_DIR/bad-patch-dir" --patch-dir does-not-exist --json >/dev/null 2>&1; then
  echo "expected missing patch dir to fail" >&2
  exit 1
fi
cat >"$STATE_DIR/worse.patch" <<'PATCH'
--- a/attempt.c
+++ b/attempt.c
@@ -5 +5 @@
-    int score = room * 17 + keys * 9;
+    int score = room * 18 + keys * 9;
PATCH
uv run --project "$ROOT" decomp-goal variants --repo "$ROOT/examples/toy_match" --unit attempt.c --state-dir "$STATE_DIR/empty-variants" --patch "$STATE_DIR/worse.patch" --keep-best --allow-dirty --json >/dev/null
git -C "$ROOT" diff --exit-code -- examples/toy_match/attempt.c >/dev/null
uv run --project "$ROOT" decomp-goal steer --repo "$ROOT/examples/toy_match" --unit attempt.start.c --source smoke --text "branch condition lead" --leads-dir "$LEADS_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal steer --repo "$ROOT/examples/toy_match" --leads-dir "$LEADS_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal decompilers --repo "$ROOT/examples/toy_match" --unit attempt.start.c --function score_room --source ghidra --file "$ROOT/examples/toy_match/decompiler-ghidra.txt" --notes "branch and constant shape agree" --confidence high --decompiler-dir "$DECOMPILER_DIR" --leads-dir "$LEADS_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal decompilers --repo "$ROOT/examples/toy_match" --unit attempt.start.c --decompiler-dir "$DECOMPILER_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal gaps --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --json >/dev/null
uv run --project "$ROOT" decomp-goal monitor --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --dashboard-out "$STATE_DIR/monitor.html" --max-ticks 1 --json >/dev/null
test -s "$STATE_DIR/monitor.html"
uv run --project "$ROOT" decomp-goal monitor --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --dashboard-out .decomp-goal/smoke-monitor.html --max-ticks 1 --json >/dev/null
test -s "$ROOT/examples/toy_match/.decomp-goal/smoke-monitor.html"
uv run --project "$ROOT" decomp-goal monitor --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --goal-html .decomp-goal/goal.html --max-ticks 1 --json >/dev/null
test -s "$ROOT/examples/toy_match/.decomp-goal/goal.html"
uv run --project "$ROOT" decomp-goal codex --repo "$ROOT/examples/toy_match" --unit attempt.c --mode exec --reasoning-effort high --prompt-file "$PROMPT_FILE" --leads-dir "$LEADS_DIR" --json >/dev/null
test -s "$PROMPT_FILE"
uv run --project "$ROOT" decomp-goal goal-html --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR" --out .decomp-goal/goal-once.html >/dev/null
test -s "$ROOT/examples/toy_match/.decomp-goal/goal-once.html"
uv run --project "$ROOT" decomp-goal run --repo "$ROOT/examples/toy_match" --unit attempt.start.c --state-dir "$STATE_DIR/watch-source" --json >"$STATE_DIR/report.json" || true
uv run --project "$ROOT" decomp-goal watch --repo "$ROOT/examples/toy_match" --unit attempt.start.c --report-json "$STATE_DIR/report.json" --state-dir "$STATE_DIR/watch" --goal-html .decomp-goal/watch-goal.html --max-ticks 1 --json >/dev/null
test -s "$ROOT/examples/toy_match/.decomp-goal/watch-goal.html"
test -s "$STATE_DIR/watch/watch-history.jsonl"
uv run --project "$ROOT" decomp-goal experiments --repo "$ROOT/examples/toy_match" --unit attempt.start.c --out .decomp-goal/smoke-experiments.md --json >/dev/null
test -s "$ROOT/examples/toy_match/.decomp-goal/smoke-experiments.md"
uv run --project "$ROOT" decomp-goal dashboard --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --out "$STATE_DIR/dashboard.html" >/dev/null
test -s "$STATE_DIR/dashboard.html"
uv run --project "$ROOT" decomp-goal dashboard --repo "$ROOT/examples/toy_match" --state-dir "$STATE_DIR" --out .decomp-goal/smoke-dashboard.html >/dev/null
test -s "$ROOT/examples/toy_match/.decomp-goal/smoke-dashboard.html"
rm -rf "$ROOT/examples/toy_match/.decomp-goal"

BUILD_ONLY="$STATE_DIR/build_only"
cp -R "$ROOT/examples/toy_match" "$BUILD_ONLY"
cat >"$BUILD_ONLY/decomp-goal.toml" <<'TOML'
[project]
name = "build-only"
adapter = "generic"
default_unit = "attempt.c"

[commands]
build = "true"
TOML
if uv run --project "$ROOT" decomp-goal run --repo "$BUILD_ONLY" --unit attempt.c --state-dir "$STATE_DIR/build-only-runs" --json >"$STATE_DIR/build-only-run.json"; then
  echo "expected build-only config to fail without score command" >&2
  exit 1
fi
grep -q "missing_score_command" "$STATE_DIR/build-only-run.json"

echo "smoke ok"
