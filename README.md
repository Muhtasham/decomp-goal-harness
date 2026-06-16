# decomp-goal-harness

## About

`decomp-goal-harness` is a lightweight command-line harness for running agent-driven matching decompilation goals. It helps find unfinished decompilation targets, generate scoped Codex goal prompts, run the local build/diff verifier, store structured progress records, and render a small progress dashboard.

It is designed for hard-mode matching projects where the goal is C/C++ source that compiles back to the same binary as the original. The harness does not include game assets, does not patch binaries, and does not decompile by itself. It gives a Codex-style agent a tight, repeatable compile-diff-edit loop.

The intended workflow is the same shape as a focused Codex `/goal` run, inspired by
[banteg](https://x.com/banteg)'s public Wind Waker matching-decomp experiments.

1. choose one translation unit or function,
2. configure/build the local decomp project,
3. run the project verifier (`objdiff`, a progress report, or a custom score command),
4. make small source edits,
5. commit only measurable improvements.

## Research context

This harness accompanies the accepted ICML 2026 Workshop DL4C paper
“Matching Decompilation as a Verifier-Guided Task for Human-Centered Coding Agents.”
The 5th Deep Learning for Code Workshop is part of ICML 2026 in Seoul, South Korea.
See the [DL4C workshop site](https://dl4c.github.io/) for venue details.

## Install locally

```bash
uv sync
```

Or run without installing:

```bash
uv run decomp-goal --help
```

The source-checkout toy demo also needs a local C compiler available as `cc`.

## Development checks

The repo uses Ruff for linting/formatting, ty for type checking, and pre-commit for local hooks.

```bash
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run ty check .
uv run pytest
uv run pre-commit run --all-files
```

Install the local git hook:

```bash
uv run pre-commit install
```

## Commands

Discover active projects from decomp.dev:

```bash
decomp-goal projects --platform gc --query "Wind Waker"
```

Find candidate GitHub task issues:

```bash
decomp-goal issues --github zeldaret/tww --label "easy object" --unclaimed
```

Inspect a worktree:

```bash
decomp-goal inspect --repo /path/to/project
```

List candidate nonmatching targets in a DTK/ZeldaRET-style project:

```bash
decomp-goal targets --repo /path/to/tww --limit 20
decomp-goal targets --repo /path/to/tww --rank --limit 20
```

Filter for one module:

```bash
decomp-goal targets --repo /path/to/tww --query d_a_obj_mmrr
```

Pick agent-sized work and print ready-to-run goal commands:

```bash
decomp-goal pick --repo /path/to/tww --limit 10
```

Check local setup blockers before starting a long run:

```bash
decomp-goal doctor --repo /path/to/tww
```

Generate a local contributor portal for people who want to help safely with an agent:

```bash
decomp-goal portal --repo /path/to/tww --out .git/decomp-goal/portal.html
```

The portal is a static HTML page for one local worktree. It shows setup readiness, candidate local targets, ready commands, and contribution boundaries. It is not a ROM upload service and does not replace maintainer review or project issue/claiming rules.

Render a scoped `/goal` prompt:

```bash
decomp-goal goal \
  --repo /path/to/tww \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --name "Mirror object" \
  --issue https://github.com/zeldaret/tww/issues/423
```

Run one configure/build/score pass and write a JSON run record:

```bash
decomp-goal run --repo /path/to/project --unit attempt.c
```

Run records are written under the repo's Git metadata path by default, e.g. `.git/decomp-goal/runs/`, so the harness does not dirty the decomp worktree.
This repo includes a root `decomp-goal.toml` wired to the toy verifier, so the harness can audit itself:

```bash
uv run decomp-goal gaps --repo .
uv run decomp-goal run --repo . --unit attempt.c
```

View the run history:

```bash
decomp-goal history --repo /path/to/project
```

Gate a progress commit on the latest verifier record:

```bash
decomp-goal checkpoint --repo /path/to/project
decomp-goal checkpoint --repo /path/to/project --commit
```

`--commit` stages and commits the current dirty worktree only when the latest saved run record beats prior history. Use it after a fresh `decomp-goal run`, not as a substitute for the verifier.
The checkpoint also verifies that the current worktree fingerprint matches the latest verifier record, so stale successful runs cannot authorize unrelated edits.

Ask the harness whether the agent is stuck and what to do next:

```bash
decomp-goal coach --repo /path/to/project
```

Classify the current diff and generate next leads:

```bash
decomp-goal lead --repo /path/to/project --unit attempt.start.c
decomp-goal lead --repo /path/to/project --unit attempt.start.c --diff-json objdiff-export.json --diff-format objdiff
```

Write a bounded last-mile experiment queue:

```bash
decomp-goal experiments --repo /path/to/project --unit src/d/actor/d_a_obj_mmrr.cpp
```

Batch-test source patch variants and revert losers:

```bash
decomp-goal variants \
  --repo /path/to/project \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --patch-dir .git/decomp-goal/variants
```

Use `--keep-best` only when you want the best improving patch left applied after the batch.

Try bounded combinations of patch variants for last-mile stalls:

```bash
decomp-goal fuzz \
  --repo /path/to/project \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --patch-dir .git/decomp-goal/variants \
  --combo-size 2 \
  --max-combos 300
```

Record an external steering lead from a human, Ghidra, IDA, Binja, GPT-Pro, or objdiff:

```bash
decomp-goal steer \
  --repo /path/to/project \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --source ida \
  --text "Decompiler agrees on the if/else shape; remaining delta looks like temp lifetime before the call."
```

Record structured decompiler output and compare agreement across tools:

```bash
decomp-goal decompilers \
  --repo /path/to/project \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --function create__6daPz_cFv \
  --source ghidra \
  --file ghidra-create.c \
  --notes "IDA and Binja agree on branch shape; remaining delta smells like stack temp lifetime."

decomp-goal decompilers --repo /path/to/project --unit src/d/actor/d_a_obj_mmrr.cpp
```

Audit current workflow gaps against the banteg-style loop:

```bash
decomp-goal gaps --repo /path/to/project
```

Run a lightweight monitor beside a long tmux/Codex session:

```bash
decomp-goal monitor \
  --repo /path/to/project \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --dashboard-out .git/decomp-goal/dashboard.html \
  --goal-html .git/decomp-goal/goal.html \
  --interval 300 \
  --max-ticks 999
```

With `--json`, monitor emits one valid JSON array containing all ticks.

Generate a local banteg-style progress dashboard:

```bash
decomp-goal dashboard --repo /path/to/project --title "Princess Zelda TU Progress"
```

The dashboard tracks exact functions, matched code, fuzzy score, blockers, and commit/head change markers from stored run records.

Generate or refresh a richer `goal.html` cockpit for a long run:

```bash
decomp-goal goal-html --repo /path/to/project --unit src/d/actor/d_a_obj_mmrr.cpp
```

It includes the goal prompt, progress chart, current coach advice, recent steering leads, recent run records, worktree state, and latest metrics. Point `monitor --goal-html ...` at the same path to refresh it during long sessions.

If another tool already writes report JSON, copy changes into harness history and refresh `goal.html`:

```bash
decomp-goal watch \
  --repo /path/to/project \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --report-json report.json \
  --goal-html .git/decomp-goal/goal.html \
  --interval 5 \
  --max-ticks 999
```

Write a goal prompt and print a Codex CLI runner command:

```bash
decomp-goal codex \
  --repo /path/to/tww \
  --unit src/d/actor/d_a_obj_mmrr.cpp \
  --name "Mirror object" \
  --issue https://github.com/zeldaret/tww/issues/423 \
  --reasoning-effort xhigh \
  --mode tmux \
  --session tww-mmrr
```

## Adapters

### Generic TOML adapter

If a repo has `decomp-goal.toml`, the harness reads shell commands from it:

```toml
[project]
name = "toy-match"
adapter = "generic"
default_unit = "attempt.c"

[commands]
build = "uv run --project ../.. python3 score.py --candidate {unit} --build-only"
score = "uv run --project ../.. python3 score.py --candidate {unit} --json"
diff = "uv run --project ../.. python3 score.py --candidate {unit} --diff"
```

The score command should print JSON with at least:

```json
{
  "matched": true,
  "score": 1.0
}
```

### DTK / ZeldaRET adapter

For projects with `configure.py` and `tools/project.py`, the harness detects a DTK-style project and runs:

```bash
python3 configure.py
ninja -v
python3 configure.py progress
```

It also parses `configure.py` for `Object(NonMatching, "...")`, `Object(Equivalent, "...")`, and ZeldaRET-style `ActorRel(NonMatching, "...")` entries to produce candidate targets.

The harness does not fetch or create original game inputs. If a project requires a legally obtained game image or extracted files, the run record reports `missing_original_input` instead of papering over it.

## Toy demo

`examples/toy_match` is a copyright-clean mini matching project for source checkouts of this repo. It compiles `original.c` and a candidate C file with fixed flags, compares the generated object bytes, and reports exact/fuzzy/prefix score.

Exact match:

```bash
uv run decomp-goal run --repo examples/toy_match --unit attempt.c
```

Known non-match:

```bash
uv run decomp-goal run --repo examples/toy_match --unit attempt.start.c
```

This fixture proves the harness loop without requiring a commercial game image. Real ZeldaRET projects still use the project verifier, usually `objdiff`.

Generate the toy dashboard:

```bash
uv run decomp-goal dashboard --repo examples/toy_match --title "Toy Match Progress"
```

## Runner model

The harness does not need to own Codex. It creates the task packet and records verifier results; Codex is one runner.

Use `codex exec` for bounded, non-interactive passes:

```bash
uv run decomp-goal codex --repo /path/to/tww --unit src/d/actor/d_a_obj_mmrr.cpp --mode exec
```

Use `tmux` plus interactive Codex for long matching sessions where steering matters:

```bash
uv run decomp-goal codex --repo /path/to/tww --unit src/d/actor/d_a_obj_mmrr.cpp --mode tmux --session tww-mmrr --launch
```

The tmux path is closer to the banteg workflow: let the agent run, inspect the dashboard/history, and inject steering when it gets stuck after a near-match or layout cascade. The generated prompt is written under the repo's Git metadata path so it can be reviewed or reused without creating untracked files.

Use `--reasoning-effort high` for normal deep runs and `--reasoning-effort xhigh` for last-mile plateaus where stronger hypotheses matter more than cost/latency.

## Banteg-inspired loop

The harness is designed around the workflow shown in banteg's Wind Waker `d_a_pz` run:

- one translation unit goal at a time,
- no fakematching or forbidden decomp tricks,
- compile/diff/score after each meaningful edit,
- commit only exact improvements, byte/prefix improvements, or structural layout unblocks,
- inject external leads when the agent is stuck: human notes, GPT-Pro notes, Ghidra, IDA, Binja, objdiff, debug maps,
- treat sudden exact-function jumps as possible layout cascades until proven,
- record the remaining mismatch class when stuck: string pool, relocation, branch shape, regalloc, weak/template ordering, inline, missing type, or missing original input.

The harness is intentionally a verifier wrapper, not an autonomous source mutator. A `/goal` agent can consume its target list, goal packet, JSON run records, and dashboard while doing the actual source edits in the project worktree.

## Contributor portal

`decomp-goal portal` is the first step toward the "support your favorite game with an AI model" workflow without creating maintainer burden. For a supported local worktree it renders:

- setup blockers from `doctor`,
- candidate local targets from `pick`,
- exact commands for goal/run/goal-html/Codex,
- hard boundaries against original-input handling, binary patching, and unreviewable edits.

The intended hosted version would be a registry and task broker over the same primitives: project adapter, setup doctor, scoped target, verifier-backed progress, and reviewable output. The local static portal keeps those rules explicit before there is any web service. The targets are ranking suggestions, not maintainer-approved claims; contributors still need to check the project's issue tracker, Discord, and contribution rules before submitting work.

## Reducing the last-mile grind

The painful part starts when a TU is nearly correct but one or two functions still refuse to match. Fuzzy score can become misleading after 99%, so the harness treats matching prefix and first mismatch offset as stronger last-mile signals when a score command reports them.

1. `decomp-goal lead` classifies the diff into mismatch classes such as string pool, branch shape, regalloc, relocation/call target, stack frame, constant/type, or unknown.
2. `decomp-goal lead --diff-json` ingests structured objdiff/asm-differ-style JSON when a project can export it.
3. `decomp-goal experiments` writes a checklist for one-hypothesis-at-a-time variants under the repo's Git metadata path.
4. `decomp-goal variants` applies patch files one at a time, runs the verifier, records metrics, and reverts non-kept variants.
5. `decomp-goal fuzz` tries bounded combinations of patch variants when the last mile needs the right combination of source edits.
6. `decomp-goal coach` watches run history for high-score plateaus and tells the agent to stop broad rewrites when it is stuck.
7. `decomp-goal monitor` runs that coaching loop periodically during tmux sessions and writes a steering prompt when intervention is needed.
8. `decomp-goal watch` copies changing external report JSON into durable harness history and refreshes `goal.html`.
9. `decomp-goal steer` and `decomp-goal decompilers` store external leads and inject the latest ones into the next generated `/goal` prompt.
10. `decomp-goal checkpoint` makes "commit every improvement" mechanical: it compares the latest run against prior history and only allows a commit when the verifier improved.

That does not eliminate the hard part, but it keeps the agent from random-walking after 99%. The expected behavior is: classify first, watch matching prefix/first mismatch, try bounded variants and combinations, revert failures, preserve only verifier improvements, and ask for a human/decompiler/debug-map lead when the same mismatch class survives several variants.

The remaining non-code boundary is original game input. The harness intentionally reports `missing_original_input`; it does not fetch, generate, or bypass copyrighted game material.

## Credits

Core idea and workflow inspiration: [banteg on X](https://x.com/banteg) / [banteg on GitHub](https://github.com/banteg), especially the public Wind Waker matching-decomp runs that showed how well scoped `/goal` agents fit this problem.

## Example TWW goal packet

```text
Get `src/d/actor/d_a_obj_mmrr.cpp` / Mirror object to 100% matching without fakematching or forbidden decomp tricks, with validation in the local worktree.

Rules:
- Use source-level decompilation changes; do not patch generated/original binaries.
- Prefer the project’s existing macros, typedefs, headers, and naming style.
- Make small commits only for measurable improvements.
- Do not mark a function or TU matching unless the local diff/build verifier proves it.
- When stuck, classify the mismatch: layout, string pool, branch shape, regalloc, weak/template ordering, relocation, inline, missing type, or missing original input.
```

## Current intended first real target

For Wind Waker, a clean first target is:

- upstream repo: `zeldaret/tww`
- fork: `Muhtasham/tww`
- target issue: https://github.com/zeldaret/tww/issues/423
- unit: `src/d/actor/d_a_obj_mmrr.cpp`

Before a real TWW matching loop can run, the local TWW worktree needs the user-provided original input under `orig/GZLE01/`, as described by the upstream README.
