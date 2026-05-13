# decomp-goal-harness

A small harness for agent-driven matching decompilation work.

The intended workflow is the same shape as a focused Codex `/goal` run:

1. choose one translation unit or function,
2. configure/build the local decomp project,
3. run the project oracle (`objdiff`, a progress report, or a custom score command),
4. make small source edits,
5. commit only measurable improvements.

The harness does not decompile by itself. It gives an agent a repeatable loop and structured run records so the hard part can stay focused on compile-diff-edit reasoning.

## Install locally

```bash
python3 -m pip install -e .
```

Or run without installing:

```bash
PYTHONPATH=src python3 -m decomp_goal --help
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
```

Filter for one module:

```bash
decomp-goal targets --repo /path/to/tww --query d_a_obj_mmrr
```

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

Run records are written to `<repo>/.decomp-goal/runs/` by default.

View the run history:

```bash
decomp-goal history --repo /path/to/project
```

Generate a local banteg-style progress dashboard:

```bash
decomp-goal dashboard --repo /path/to/project --title "Princess Zelda TU Progress"
```

The dashboard tracks exact functions, matched code, fuzzy score, blockers, and commit/head change markers from stored run records.

## Adapters

### Generic TOML adapter

If a repo has `decomp-goal.toml`, the harness reads shell commands from it:

```toml
[project]
name = "toy-match"
adapter = "generic"
default_unit = "attempt.c"

[commands]
build = "python3 score.py --candidate {unit} --build-only"
score = "python3 score.py --candidate {unit} --json"
diff = "python3 score.py --candidate {unit} --diff"
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

`examples/toy_match` is a copyright-clean mini matching project. It compiles `original.c` and a candidate C file with fixed flags, compares the generated object bytes, and reports exact/fuzzy score.

Exact match:

```bash
PYTHONPATH=src python3 -m decomp_goal run --repo examples/toy_match --unit attempt.c
```

Known non-match:

```bash
PYTHONPATH=src python3 -m decomp_goal run --repo examples/toy_match --unit attempt.start.c
```

This fixture proves the harness loop without requiring a commercial game image. Real ZeldaRET projects still use the project oracle, usually `objdiff`.

Generate the toy dashboard:

```bash
PYTHONPATH=src python3 -m decomp_goal dashboard --repo examples/toy_match --title "Toy Match Progress"
```

## Banteg-inspired loop

The harness is designed around the workflow shown in the Wind Waker `d_a_pz` run:

- one translation unit goal at a time,
- no fakematching or forbidden decomp tricks,
- compile/diff/score after each meaningful edit,
- commit only exact improvements, fuzzy improvements, or structural layout unblocks,
- treat sudden exact-function jumps as possible layout cascades until proven,
- record the remaining mismatch class when stuck: string pool, relocation, branch shape, regalloc, weak/template ordering, inline, missing type, or missing original input.

The harness is intentionally an oracle wrapper, not an autonomous source mutator. A `/goal` agent can consume its target list, goal packet, JSON run records, and dashboard while doing the actual source edits in the project worktree.

## Example TWW goal packet

```text
Get `src/d/actor/d_a_obj_mmrr.cpp` / Mirror object to 100% matching without fakematching or forbidden decomp tricks, with validation in the local worktree.

Rules:
- Use source-level decompilation changes; do not patch generated/original binaries.
- Prefer the project’s existing macros, typedefs, headers, and naming style.
- Make small commits only for measurable improvements.
- Do not mark a function or TU matching unless the local diff/build oracle proves it.
- When stuck, classify the mismatch: layout, string pool, branch shape, regalloc, weak/template ordering, relocation, inline, missing type, or missing original input.
```

## Current intended first real target

For Wind Waker, a clean first target is:

- upstream repo: `zeldaret/tww`
- fork: `Muhtasham/tww`
- target issue: https://github.com/zeldaret/tww/issues/423
- unit: `src/d/actor/d_a_obj_mmrr.cpp`

Before a real TWW matching loop can run, the local TWW worktree needs the user-provided original input under `orig/GZLE01/`, as described by the upstream README.
