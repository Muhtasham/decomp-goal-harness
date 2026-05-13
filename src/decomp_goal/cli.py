from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NON_MATCHING_RE = re.compile(
    r"Object\(\s*(?P<status>NonMatching|Equivalent)\s*,\s*[\"'](?P<path>[^\"']+)[\"']"
)
ACTOR_REL_RE = re.compile(
    r"ActorRel\(\s*(?P<status>NonMatching|Equivalent)\s*,\s*[\"'](?P<name>[^\"']+)[\"']"
)


@dataclass
class CommandResult:
    name: str
    command: str
    exit_code: int
    elapsed_seconds: float
    stdout: str
    stderr: str

    @property
    def combined_output(self) -> str:
        return "\n".join(part for part in [self.stdout, self.stderr] if part)


def repo_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise argparse.ArgumentTypeError(f"repo path does not exist: {path}")
    return path


def load_config(repo: Path) -> dict[str, Any]:
    config_path = repo / "decomp-goal.toml"
    if not config_path.exists():
        return {}
    with config_path.open("rb") as f:
        return tomllib.load(f)


def detect_adapter(repo: Path, config: dict[str, Any]) -> str:
    configured = config.get("project", {}).get("adapter")
    if configured:
        return str(configured)
    if (repo / "configure.py").exists() and (repo / "tools" / "project.py").exists():
        return "dtk"
    return "generic"


def run_command(name: str, command: str, cwd: Path, unit: str | None = None) -> CommandResult:
    rendered = render_command(command, unit)
    start = time.monotonic()
    proc = subprocess.run(
        rendered,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
    )
    elapsed = time.monotonic() - start
    return CommandResult(
        name=name,
        command=rendered,
        exit_code=proc.returncode,
        elapsed_seconds=round(elapsed, 3),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def render_command(command: str, unit: str | None) -> str:
    if unit is None:
        return command
    return command.replace("{unit}", shlex.quote(unit))


def git_info(repo: Path) -> dict[str, str | None]:
    def git(args: list[str]) -> str | None:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    return {
        "branch": git(["branch", "--show-current"]),
        "head": git(["rev-parse", "--short", "HEAD"]),
        "remote": git(["remote", "get-url", "origin"]),
        "dirty": "true" if git(["status", "--short"]) else "false",
    }


def inspect_repo(repo: Path) -> dict[str, Any]:
    config = load_config(repo)
    adapter = detect_adapter(repo, config)
    info: dict[str, Any] = {
        "repo": str(repo),
        "adapter": adapter,
        "project": config.get("project", {}),
        "git": git_info(repo),
        "tools": {
            "git": shutil.which("git"),
            "python3": shutil.which("python3"),
            "python": shutil.which("python"),
            "ninja": shutil.which("ninja"),
            "cc": shutil.which("cc"),
        },
    }
    if adapter == "dtk":
        info["dtk"] = inspect_dtk(repo)
    else:
        info["generic"] = inspect_generic(repo, config)
    return info


def inspect_dtk(repo: Path) -> dict[str, Any]:
    default_version = "GZLE01"
    rels_arc = repo / "orig" / default_version / "files" / "RELS.arc"
    original_entries = []
    orig_root = repo / "orig" / default_version
    if orig_root.exists():
        original_entries = [
            str(path.relative_to(orig_root))
            for path in orig_root.rglob("*")
            if path.name != ".gitkeep"
        ][:20]
    return {
        "configure_py": (repo / "configure.py").exists(),
        "build_ninja": (repo / "build.ninja").exists(),
        "objdiff_json": (repo / "objdiff.json").exists(),
        "default_version": default_version,
        "expected_rels_arc": str(rels_arc),
        "has_original_input": rels_arc.exists(),
        "original_entries_sample": original_entries,
    }


def inspect_generic(repo: Path, config: dict[str, Any]) -> dict[str, Any]:
    commands = config.get("commands", {})
    return {
        "config": (repo / "decomp-goal.toml").exists(),
        "commands": sorted(commands.keys()),
        "default_unit": config.get("project", {}).get("default_unit"),
    }


def list_targets(repo: Path, limit: int | None = None, query: str | None = None) -> list[dict[str, str]]:
    config = load_config(repo)
    adapter = detect_adapter(repo, config)
    if adapter == "dtk":
        return list_dtk_targets(repo, limit, query)
    default_unit = config.get("project", {}).get("default_unit")
    if default_unit:
        targets = [{"status": "Configured", "path": str(default_unit)}]
        if query:
            targets = [target for target in targets if query in target["path"]]
        return targets
    return []


def list_dtk_targets(repo: Path, limit: int | None, query: str | None) -> list[dict[str, str]]:
    configure = repo / "configure.py"
    if not configure.exists():
        return []
    targets = []
    for line_no, line in enumerate(configure.read_text(encoding="utf-8").splitlines(), 1):
        match = NON_MATCHING_RE.search(line)
        actor_match = ACTOR_REL_RE.search(line)
        if match:
            target = {
                "status": match.group("status"),
                "path": match.group("path"),
                "line": str(line_no),
                "kind": "object",
            }
        elif actor_match:
            rel_name = actor_match.group("name")
            target = {
                "status": actor_match.group("status"),
                "path": f"d/actor/{rel_name}.cpp",
                "line": str(line_no),
                "kind": "actor_rel",
            }
        else:
            continue
        if query and query not in target["path"]:
            continue
        targets.append(target)
        if limit and len(targets) >= limit:
            break
    return targets


def render_goal(repo: Path, unit: str | None, name: str | None, issue: str | None) -> str:
    config = load_config(repo)
    adapter = detect_adapter(repo, config)
    project_name = name or config.get("project", {}).get("name") or repo.name
    unit = unit or config.get("project", {}).get("default_unit") or "<target source file>"
    issue_text = f"\nUpstream issue/context: {issue}" if issue else ""
    if adapter == "dtk":
        validation = "Run `python3 configure.py`, `ninja`, then inspect objdiff/progress for the target TU."
    else:
        validation = "Run `decomp-goal run --repo . --unit <unit>` and require an exact match score."
    return f"""Get `{unit}` / {project_name} to 100% matching without fakematching or forbidden decomp tricks, with validation in the local worktree.{issue_text}

Rules:
- Use source-level decompilation changes; do not patch generated/original binaries.
- Prefer the project’s existing macros, typedefs, headers, and naming style.
- Make small commits only for measurable improvements.
- Do not mark a function or TU matching unless the local diff/build oracle proves it.
- When stuck, classify the mismatch: layout, string pool, branch shape, regalloc, weak/template ordering, relocation, inline, missing type, or missing original input.

Validation:
- {validation}
"""


def run_harness(repo: Path, unit: str | None, state_dir: Path, json_output: bool) -> int:
    config = load_config(repo)
    adapter = detect_adapter(repo, config)
    if adapter == "dtk":
        result = run_dtk(repo, unit)
    else:
        result = run_generic(repo, config, unit)
    write_run_record(result, state_dir)
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print_human_run(result)
    return 0 if result.get("matched") is True else 1


def run_generic(repo: Path, config: dict[str, Any], unit: str | None) -> dict[str, Any]:
    commands = config.get("commands", {})
    if not commands:
        return base_result(repo, "generic", unit, matched=False, blocker="missing_decomp_goal_toml")
    unit = unit or config.get("project", {}).get("default_unit")
    if not unit:
        return base_result(repo, "generic", unit, matched=False, blocker="missing_unit")

    command_results: list[CommandResult] = []
    for name in ["configure", "build", "score"]:
        command = commands.get(name)
        if not command:
            continue
        res = run_command(name, command, repo, unit)
        command_results.append(res)
        if res.exit_code != 0:
            return finish_result(repo, "generic", unit, command_results, matched=False, blocker=f"{name}_failed")

    score = parse_score(command_results[-1].stdout if command_results else "")
    matched = score.get("matched") is True
    return finish_result(repo, "generic", unit, command_results, matched=matched, score=score)


def run_dtk(repo: Path, unit: str | None) -> dict[str, Any]:
    command_results: list[CommandResult] = []
    commands = [
        ("configure", "python3 configure.py"),
        ("build", "ninja -v"),
    ]
    for name, command in commands:
        res = run_command(name, command, repo, unit)
        command_results.append(res)
        if res.exit_code != 0:
            return finish_result(
                repo,
                "dtk",
                unit,
                command_results,
                matched=False,
                blocker=classify_blocker(res.combined_output),
            )

    progress = run_command("progress", "python3 configure.py progress", repo, unit)
    command_results.append(progress)
    score = parse_dtk_progress(progress.stdout)
    return finish_result(repo, "dtk", unit, command_results, matched=None, score=score)


def parse_score(stdout: str) -> dict[str, Any]:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"matched": None, "raw": stdout.strip()}


def parse_dtk_progress(stdout: str) -> dict[str, Any]:
    categories: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith("files)") and " matched, " in stripped:
            if current:
                categories.append(current)
            current = {"summary": stripped}
        elif current is not None and (stripped.startswith("Code:") or stripped.startswith("Data:")):
            key = "code" if stripped.startswith("Code:") else "data"
            current[key] = stripped
    if current:
        categories.append(current)
    return {"progress_categories": categories, "raw": stdout.strip()}


def classify_blocker(output: str) -> str:
    lowered = output.lower()
    if "rels.arc not found" in lowered or "orig/" in lowered and "not found" in lowered:
        return "missing_original_input"
    if "ninja: command not found" in lowered:
        return "missing_ninja"
    if "python3: command not found" in lowered:
        return "missing_python3"
    return "command_failed"


def base_result(
    repo: Path,
    adapter: str,
    unit: str | None,
    matched: bool | None,
    blocker: str | None = None,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "adapter": adapter,
        "unit": unit,
        "git": git_info(repo),
        "matched": matched,
        "blocker": blocker,
        "commands": [],
    }


def finish_result(
    repo: Path,
    adapter: str,
    unit: str | None,
    command_results: list[CommandResult],
    matched: bool | None,
    blocker: str | None = None,
    score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = base_result(repo, adapter, unit, matched, blocker)
    result["commands"] = [asdict(command) for command in command_results]
    if score is not None:
        result["score"] = score
    return result


def write_run_record(result: dict[str, Any], state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_adapter = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(result.get("adapter") or "run"))
    path = state_dir / f"{stamp}-{safe_adapter}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def print_human_run(result: dict[str, Any]) -> None:
    print(f"adapter: {result['adapter']}")
    print(f"repo: {result['repo']}")
    if result.get("unit"):
        print(f"unit: {result['unit']}")
    print(f"matched: {result.get('matched')}")
    if result.get("blocker"):
        print(f"blocker: {result['blocker']}")
    score = result.get("score")
    if score:
        if "score" in score:
            print(f"score: {score['score']}")
        if "exact_bytes" in score and "total_bytes" in score:
            print(f"bytes: {score['exact_bytes']} / {score['total_bytes']}")
    for command in result.get("commands", []):
        print(f"[{command['name']}] exit={command['exit_code']} {command['command']}")
        output = "\n".join(part for part in [command.get("stdout", ""), command.get("stderr", "")] if part)
        if output:
            print(output.strip()[-2000:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decomp-goal")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Inspect a matching-decomp worktree")
    inspect_p.add_argument("--repo", type=repo_path, default=Path.cwd())
    inspect_p.add_argument("--json", action="store_true")

    targets_p = sub.add_parser("targets", help="List candidate nonmatching targets")
    targets_p.add_argument("--repo", type=repo_path, default=Path.cwd())
    targets_p.add_argument("--limit", type=int, default=40)
    targets_p.add_argument("--query")
    targets_p.add_argument("--json", action="store_true")

    goal_p = sub.add_parser("goal", help="Render a /goal prompt packet")
    goal_p.add_argument("--repo", type=repo_path, default=Path.cwd())
    goal_p.add_argument("--unit")
    goal_p.add_argument("--name")
    goal_p.add_argument("--issue")

    run_p = sub.add_parser("run", help="Run configure/build/score once")
    run_p.add_argument("--repo", type=repo_path, default=Path.cwd())
    run_p.add_argument("--unit")
    run_p.add_argument("--state-dir", type=Path, default=Path(".decomp-goal/runs"))
    run_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        info = inspect_repo(args.repo)
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print(json.dumps(info, indent=2))
        return 0
    if args.command == "targets":
        targets = list_targets(args.repo, args.limit, args.query)
        if args.json:
            print(json.dumps(targets, indent=2))
        else:
            for target in targets:
                kind = target.get("kind", "")
                print(f"{target.get('status', ''):12} {target.get('path')} {target.get('line', '')} {kind}")
        return 0
    if args.command == "goal":
        print(render_goal(args.repo, args.unit, args.name, args.issue).strip())
        return 0
    if args.command == "run":
        return run_harness(args.repo, args.unit, args.state_dir, args.json)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
