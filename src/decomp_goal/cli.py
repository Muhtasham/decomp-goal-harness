from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import shlex
import shutil
import subprocess
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


NON_MATCHING_RE = re.compile(
    r"Object\(\s*(?P<status>NonMatching|Equivalent)\s*,\s*[\"'](?P<path>[^\"']+)[\"']"
)
ACTOR_REL_RE = re.compile(
    r"ActorRel\(\s*(?P<status>NonMatching|Equivalent)\s*,\s*[\"'](?P<name>[^\"']+)[\"']"
)
ARTICLE_RE = re.compile(r"<article class=\"project\"(?P<attrs>.*?)</article>", re.S)
ATTR_RE = re.compile(r"(?P<name>[a-zA-Z0-9_-]+)=\"(?P<value>[^\"]*)\"")
CLAIM_RE = re.compile(
    r"\b(i('|’)ll|i will|i am|i'm|im|taking|working|on this|on it|have a go|giving it a try|try it|take a crack)\b",
    re.I,
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


def strip_tags(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html_lib.unescape(without_tags)).strip()


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


def fetch_decompdev_projects(query: str | None, platform: str | None, limit: int) -> list[dict[str, Any]]:
    req = Request("https://decomp.dev/projects", headers={"User-Agent": "decomp-goal-harness/0.1"})
    with urlopen(req, timeout=30) as response:
        html = response.read().decode("utf-8", "replace")

    projects: list[dict[str, Any]] = []
    for match in ARTICLE_RE.finditer(html):
        article = match.group(0)
        attrs = {m.group("name"): html_lib.unescape(m.group("value")) for m in ATTR_RE.finditer(match.group("attrs"))}
        project_platform = attrs.get("data-platform")
        if platform and project_platform != platform:
            continue

        title_match = re.search(r"<h3 class=\"project-title\">(?P<title>.*?)</h3>", article, re.S)
        href_match = re.search(r"<a class=\"project-link\" href=\"(?P<href>[^\"]+)\"", article)
        summary_match = re.search(r"<h6>(?P<summary>.*?)</h6>", article, re.S)
        commit_match = re.search(r'href="(?P<commit_url>https://github.com/[^"]+/commit/(?P<sha>[a-f0-9]+))"', article)
        updated_match = re.search(r'<span title="(?P<updated>[^"]+)">Updated (?P<updated_relative>.*?)</span>', article, re.S)
        if not title_match or not href_match:
            continue

        title = strip_tags(title_match.group("title"))
        if query and query.lower() not in title.lower() and query.lower() not in href_match.group("href").lower():
            continue

        href = href_match.group("href")
        repo = None
        if href.startswith("https://decomp.dev/"):
            slug = href.removeprefix("https://decomp.dev/").strip("/")
            if slug.count("/") == 1:
                repo = slug

        projects.append(
            {
                "title": title,
                "platform": project_platform,
                "summary": strip_tags(summary_match.group("summary")) if summary_match else None,
                "decompdev_url": href,
                "github_repo": repo,
                "commit": commit_match.group("sha")[:7] if commit_match else None,
                "commit_url": commit_match.group("commit_url") if commit_match else None,
                "updated_at": updated_match.group("updated") if updated_match else None,
                "updated": strip_tags(updated_match.group("updated_relative")) if updated_match else None,
            }
        )
        if limit and len(projects) >= limit:
            break
    return projects


def list_github_issues(
    repo_slug: str,
    label: str | None,
    limit: int,
    unclaimed: bool,
) -> list[dict[str, Any]]:
    if shutil.which("gh") is None:
        raise SystemExit("gh not found; install GitHub CLI or skip GitHub issue discovery")
    cmd = [
        "gh",
        "issue",
        "list",
        "-R",
        repo_slug,
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number,title,labels,url,updatedAt",
    ]
    if label:
        cmd.extend(["--label", label])
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip())
    issues = json.loads(proc.stdout)
    if not unclaimed:
        return issues

    filtered = []
    for issue in issues:
        view = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(issue["number"]),
                "-R",
                repo_slug,
                "--json",
                "comments",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if view.returncode != 0:
            issue["claim_status"] = "unknown"
            filtered.append(issue)
            continue
        comments = json.loads(view.stdout).get("comments", [])
        claim_comments = [
            {
                "author": comment.get("author", {}).get("login"),
                "body": comment.get("body", ""),
                "url": comment.get("url"),
            }
            for comment in comments
            if CLAIM_RE.search(comment.get("body", ""))
        ]
        issue["claim_status"] = "claimed" if claim_comments else "unclaimed"
        issue["claim_comments"] = claim_comments
        if not claim_comments:
            filtered.append(issue)
    return filtered


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
- Make small commits only for measurable improvements: exact function count, matched bytes, fuzzy score, or a documented layout unblocker.
- Do not mark a function or TU matching unless the local diff/build oracle proves it.
- When stuck, classify the mismatch: layout, string pool, branch shape, regalloc, weak/template ordering, relocation, inline, missing type, or missing original input.
- Treat layout cascades carefully: a tiny function body can realign downstream code and create large apparent jumps.
- Record near-matches with the exact remaining delta instead of hiding them behind fake source tricks.

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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_adapter = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(result.get("adapter") or "run"))
    path = state_dir / f"{stamp}-{safe_adapter}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def load_history(state_dir: Path) -> list[dict[str, Any]]:
    if not state_dir.exists():
        return []
    records = []
    for path in sorted(state_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        record["_path"] = str(path)
        metrics = extract_metrics(record)
        record["_metrics"] = metrics
        records.append(record)
    records.sort(key=lambda record: record.get("created_at", ""))
    return records


def extract_metrics(record: dict[str, Any]) -> dict[str, Any]:
    score = record.get("score") or {}
    metrics: dict[str, Any] = {
        "matched_code_percent": None,
        "fuzzy_percent": None,
        "exact_functions": None,
        "total_functions": None,
        "matched_code": None,
        "total_code": None,
    }

    if "exact_bytes" in score and "total_bytes" in score and score.get("total_bytes"):
        exact = int(score["exact_bytes"])
        total = int(score["total_bytes"])
        metrics["matched_code"] = exact
        metrics["total_code"] = total
        metrics["matched_code_percent"] = exact / total * 100
        if isinstance(score.get("score"), (int, float)):
            metrics["fuzzy_percent"] = float(score["score"]) * 100
        metrics["exact_functions"] = 1 if record.get("matched") else 0
        metrics["total_functions"] = 1

    if "progress_categories" in score:
        categories = score.get("progress_categories") or []
        if categories:
            first = categories[0]
            code_line = first.get("code")
            if code_line:
                code_match = re.search(
                    r"Code:\s+(?P<matched>\d+)\s+/\s+(?P<total>\d+)\s+bytes\s+\((?P<funcs>\d+)\s+/\s+(?P<total_funcs>\d+)\s+functions\)",
                    code_line,
                )
                if code_match:
                    matched = int(code_match.group("matched"))
                    total = int(code_match.group("total"))
                    metrics["matched_code"] = matched
                    metrics["total_code"] = total
                    metrics["matched_code_percent"] = matched / total * 100 if total else None
                    metrics["exact_functions"] = int(code_match.group("funcs"))
                    metrics["total_functions"] = int(code_match.group("total_funcs"))
    return metrics


def summarize_history(records: list[dict[str, Any]]) -> dict[str, Any]:
    last = records[-1] if records else None
    best_code = None
    best_fuzzy = None
    last_progress_at = None
    previous_code = None
    for record in records:
        metrics = record.get("_metrics") or extract_metrics(record)
        code = metrics.get("matched_code_percent")
        fuzzy = metrics.get("fuzzy_percent")
        improved = False
        if code is not None and (best_code is None or code > best_code):
            best_code = code
            improved = True
        if fuzzy is not None and (best_fuzzy is None or fuzzy > best_fuzzy):
            best_fuzzy = fuzzy
            improved = True
        if previous_code is not None and code is not None and code > previous_code:
            improved = True
        if improved:
            last_progress_at = record.get("created_at")
        if code is not None:
            previous_code = code
    return {
        "runs": len(records),
        "last_run": last.get("created_at") if last else None,
        "last_progress": last_progress_at,
        "best_matched_code_percent": best_code,
        "best_fuzzy_percent": best_fuzzy,
        "last_blocker": last.get("blocker") if last else None,
        "last_matched": last.get("matched") if last else None,
    }


def print_history(records: list[dict[str, Any]]) -> None:
    if not records:
        print("no run records")
        return
    for record in records:
        metrics = record.get("_metrics") or {}
        code = metrics.get("matched_code_percent")
        fuzzy = metrics.get("fuzzy_percent")
        code_text = f"{code:.2f}%" if code is not None else "-"
        fuzzy_text = f"{fuzzy:.2f}%" if fuzzy is not None else "-"
        head = (record.get("git") or {}).get("head") or "-"
        blocker = record.get("blocker") or "-"
        print(f"{record.get('created_at')} {head} matched={record.get('matched')} code={code_text} fuzzy={fuzzy_text} blocker={blocker}")


def generate_dashboard(records: list[dict[str, Any]], title: str) -> str:
    summary = summarize_history(records)
    last_metrics = (records[-1].get("_metrics") or {}) if records else {}
    last_code = fmt_pct(last_metrics.get("matched_code_percent")) if records else "-"
    last_fuzzy = fmt_pct(last_metrics.get("fuzzy_percent")) if records else "-"
    last_exact = fmt_exact(records[-1] if records else None)
    points = []
    for idx, record in enumerate(records):
        metrics = record.get("_metrics") or {}
        code = metrics.get("matched_code_percent")
        fuzzy = metrics.get("fuzzy_percent")
        exact = None
        if metrics.get("exact_functions") is not None and metrics.get("total_functions"):
            exact = metrics["exact_functions"] / metrics["total_functions"] * 100
        points.append(
            {
                "idx": idx,
                "created_at": record.get("created_at"),
                "head": (record.get("git") or {}).get("head"),
                "subject": record.get("blocker") or ("matched" if record.get("matched") else "run"),
                "code": code,
                "fuzzy": fuzzy,
                "exact": exact,
            }
        )

    chart = render_svg_chart(points)
    rows = "\n".join(
        f"<tr><td>{html_lib.escape(str(p['head'] or '-'))}</td><td>{fmt_pct(p['exact'])}</td><td>{fmt_pct(p['code'])}</td><td>{fmt_pct(p['fuzzy'])}</td><td>{html_lib.escape(str(p['subject']))}</td></tr>"
        for p in reversed(points[-30:])
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_lib.escape(title)}</title>
  <style>
    body {{ margin: 0; font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f1ea; color: #20232d; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    .muted {{ color: #6f7480; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin: 24px 0; }}
    .card {{ background: #fff; border: 1px solid #d8d4cb; border-radius: 8px; padding: 18px; }}
    .label {{ color: #6f7480; font-size: 14px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }}
    .value {{ font-size: 42px; font-weight: 800; margin-top: 8px; }}
    .chart {{ background: #fff; border: 1px solid #d8d4cb; border-radius: 8px; padding: 18px; overflow-x: auto; }}
    .legend {{ display: flex; gap: 22px; flex-wrap: wrap; color: #626873; margin-bottom: 12px; }}
    .dot {{ display: inline-block; width: 13px; height: 13px; border-radius: 50%; margin-right: 8px; vertical-align: -1px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 18px; background: #fff; border: 1px solid #d8d4cb; border-radius: 8px; overflow: hidden; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #e8e4dc; }}
    th {{ color: #6f7480; font-size: 13px; text-transform: uppercase; }}
    @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} .value {{ font-size: 30px; }} }}
  </style>
</head>
<body>
<main>
  <h1>{html_lib.escape(title)}</h1>
  <div class="muted">{summary['runs']} runs · last run {html_lib.escape(str(summary['last_run'] or '-'))}</div>
  <section class="grid">
    <div class="card"><div class="label">Exact Functions</div><div class="value">{last_exact}</div></div>
    <div class="card"><div class="label">Matched Code</div><div class="value">{last_code}</div></div>
    <div class="card"><div class="label">Fuzzy Match</div><div class="value">{last_fuzzy}</div></div>
    <div class="card"><div class="label">Last Blocker</div><div class="value" style="font-size:24px">{html_lib.escape(str(summary['last_blocker'] or '-'))}</div></div>
  </section>
  <section class="chart">
    <div class="legend">
      <span><span class="dot" style="background:#316bc5"></span>Matched code %</span>
      <span><span class="dot" style="background:#3e8f60"></span>Exact functions %</span>
      <span><span class="dot" style="background:#b46b1d"></span>Fuzzy %</span>
      <span><span class="dot" style="background:#858c97"></span>Commit/change points</span>
    </div>
    {chart}
  </section>
  <table>
    <thead><tr><th>Point</th><th>Exact</th><th>Code</th><th>Fuzzy</th><th>Subject</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</main>
</body>
</html>
"""


def fmt_pct(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def fmt_exact(record: dict[str, Any] | None) -> str:
    if not record:
        return "-"
    metrics = record.get("_metrics") or {}
    exact = metrics.get("exact_functions")
    total = metrics.get("total_functions")
    if exact is None or total is None:
        return "-"
    return f"{exact}/{total}"


def render_svg_chart(points: list[dict[str, Any]]) -> str:
    width = max(720, 80 + max(1, len(points) - 1) * 42)
    height = 360
    left = 48
    right = 18
    top = 18
    bottom = 34
    plot_w = width - left - right
    plot_h = height - top - bottom

    def xy(idx: int, value: float) -> tuple[float, float]:
        x = left + (idx / max(1, len(points) - 1)) * plot_w
        y = top + (100 - max(0, min(100, value))) / 100 * plot_h
        return x, y

    def path_for(key: str) -> str:
        pairs = [(p["idx"], p.get(key)) for p in points if p.get(key) is not None]
        if not pairs:
            return ""
        coords = [xy(idx, float(value)) for idx, value in pairs]
        return " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))

    grid = []
    for pct in [0, 20, 40, 60, 80, 100]:
        _, y = xy(0, pct)
        grid.append(f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#d8d4cb"/>')
        grid.append(f'<text x="8" y="{y+4:.1f}" fill="#6f7480" font-size="12">{pct}%</text>')
    commit_lines = []
    last_head = None
    for point in points:
        head = point.get("head")
        if head and head != last_head:
            x, _ = xy(point["idx"], 0)
            commit_lines.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{height-bottom}" stroke="#858c97" opacity=".35"/>')
            last_head = head
    return f"""<svg width="{width}" height="{height}" role="img" aria-label="progress chart">
  {"".join(grid)}
  {"".join(commit_lines)}
  <path d="{path_for('code')}" fill="none" stroke="#316bc5" stroke-width="3"/>
  <path d="{path_for('exact')}" fill="none" stroke="#3e8f60" stroke-width="3"/>
  <path d="{path_for('fuzzy')}" fill="none" stroke="#b46b1d" stroke-width="3"/>
</svg>"""


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

    projects_p = sub.add_parser("projects", help="Discover matching decomp projects from decomp.dev")
    projects_p.add_argument("--query")
    projects_p.add_argument("--platform", help="decomp.dev platform id, for example gc, n64, wii")
    projects_p.add_argument("--limit", type=int, default=20)
    projects_p.add_argument("--json", action="store_true")

    issues_p = sub.add_parser("issues", help="List GitHub task issues for a decomp repo")
    issues_p.add_argument("--github", required=True, help="GitHub repo slug, for example zeldaret/tww")
    issues_p.add_argument("--label", default="easy object")
    issues_p.add_argument("--limit", type=int, default=30)
    issues_p.add_argument("--unclaimed", action="store_true")
    issues_p.add_argument("--json", action="store_true")

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
    run_p.add_argument("--state-dir", type=Path)
    run_p.add_argument("--json", action="store_true")

    history_p = sub.add_parser("history", help="Print stored run history")
    history_p.add_argument("--repo", type=repo_path, default=Path.cwd())
    history_p.add_argument("--state-dir", type=Path)
    history_p.add_argument("--json", action="store_true")

    dashboard_p = sub.add_parser("dashboard", help="Generate a local HTML progress dashboard")
    dashboard_p.add_argument("--repo", type=repo_path, default=Path.cwd())
    dashboard_p.add_argument("--state-dir", type=Path)
    dashboard_p.add_argument("--out", type=Path)
    dashboard_p.add_argument("--title", default="Decomp Goal Progress")

    args = parser.parse_args(argv)
    if args.command == "projects":
        projects = fetch_decompdev_projects(args.query, args.platform, args.limit)
        if args.json:
            print(json.dumps(projects, indent=2))
        else:
            for project in projects:
                repo = project.get("github_repo") or "-"
                summary = project.get("summary") or "-"
                updated = project.get("updated") or "-"
                print(f"{project['title']} | {repo} | {summary} | updated {updated}")
        return 0
    if args.command == "issues":
        issues = list_github_issues(args.github, args.label, args.limit, args.unclaimed)
        if args.json:
            print(json.dumps(issues, indent=2))
        else:
            for issue in issues:
                claim = issue.get("claim_status", "")
                claim_text = f" [{claim}]" if claim else ""
                print(f"#{issue['number']} {issue['title']}{claim_text} {issue['url']}")
        return 0
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
        state_dir = (args.state_dir or (args.repo / ".decomp-goal" / "runs")).resolve()
        return run_harness(args.repo, args.unit, state_dir, args.json)
    if args.command == "history":
        state_dir = (args.state_dir or (args.repo / ".decomp-goal" / "runs")).resolve()
        records = load_history(state_dir)
        if args.json:
            print(json.dumps({"summary": summarize_history(records), "runs": records}, indent=2))
        else:
            print_history(records)
        return 0
    if args.command == "dashboard":
        state_dir = (args.state_dir or (args.repo / ".decomp-goal" / "runs")).resolve()
        out = (args.out or (args.repo / ".decomp-goal" / "dashboard.html")).resolve()
        records = load_history(state_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(generate_dashboard(records, args.title), encoding="utf-8")
        print(out)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
