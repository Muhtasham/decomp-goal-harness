from __future__ import annotations

import json
import subprocess
from pathlib import Path

from decomp_goal.cli import (
    apply_patch_set,
    build_gap_report,
    dtk_progress_matched,
    extract_metrics,
    generate_contributor_portal,
    metric_tuple,
    normalize_external_report,
    parse_dtk_progress,
    patch_combinations,
    repo_relative_or_default,
    run_generic,
    run_watch,
)


def test_dtk_progress_aggregates_multiple_categories() -> None:
    score = parse_dtk_progress(
        """
main: 1 matched, 1 total (1 files)
Code: 10 / 20 bytes (1 / 2 functions)
Data: 4 / 4 bytes
rels: 1 matched, 1 total (1 files)
Code: 5 / 10 bytes (1 / 2 functions)
Data: 2 / 2 bytes
""".strip()
    )

    metrics = extract_metrics({"score": score, "matched": False})

    assert metrics["matched_code"] == 15
    assert metrics["total_code"] == 30
    assert metrics["exact_functions"] == 2
    assert metrics["total_functions"] == 4
    assert dtk_progress_matched(score) is False


def test_dtk_progress_can_mark_exact_when_all_code_and_data_match() -> None:
    score = parse_dtk_progress(
        """
main: 1 matched, 1 total (1 files)
Code: 20 / 20 bytes (2 / 2 functions)
Data: 4 / 4 bytes
""".strip()
    )

    assert dtk_progress_matched(score) is True


def test_generic_build_only_config_is_not_a_score_oracle(tmp_path: Path) -> None:
    result = run_generic(
        tmp_path,
        {
            "project": {"default_unit": "attempt.c"},
            "commands": {"build": "true"},
        },
        None,
    )

    assert result["matched"] is False
    assert result["blocker"] == "missing_score_command"


def test_gaps_require_generic_score_command(tmp_path: Path) -> None:
    (tmp_path / "decomp-goal.toml").write_text(
        """
[project]
name = "build-only"
adapter = "generic"
default_unit = "attempt.c"

[commands]
build = "true"
""".strip(),
        encoding="utf-8",
    )

    report = build_gap_report(tmp_path, tmp_path / "state")
    oracle = next(item for item in report["gaps"] if item["area"] == "oracle loop")

    assert oracle["status"] == "open"
    assert "score" in oracle["next"]


def test_repo_relative_output_paths_use_repo_not_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert (
        repo_relative_or_default(repo, Path(".decomp-goal/goal.html"), tmp_path / "fallback")
        == (repo / ".decomp-goal" / "goal.html").resolve()
    )


def test_prefix_metrics_are_extracted_and_ranked_before_fuzzy() -> None:
    weaker_prefix = {
        "matched": False,
        "score": {
            "exact_bytes": 99,
            "total_bytes": 100,
            "score": 0.99,
            "matching_prefix_bytes": 10,
            "first_mismatch_offset": 10,
        },
    }
    stronger_prefix = {
        "matched": False,
        "score": {
            "exact_bytes": 99,
            "total_bytes": 100,
            "score": 0.98,
            "matching_prefix_bytes": 80,
            "first_mismatch_offset": 80,
        },
    }

    metrics = extract_metrics(stronger_prefix)

    assert metrics["matching_prefix_bytes"] == 80
    assert metrics["matching_prefix_percent"] == 80
    assert metrics["first_mismatch_offset"] == 80
    assert metric_tuple(stronger_prefix) > metric_tuple(weaker_prefix)


def test_patch_combinations_are_bounded(tmp_path: Path) -> None:
    patches = [tmp_path / f"{idx}.patch" for idx in range(4)]

    combos = patch_combinations(patches, combo_size=2, max_combos=3)

    assert combos == [(patches[0], patches[1]), (patches[0], patches[2]), (patches[0], patches[3])]


def test_external_report_normalizes_score_payload(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    report = tmp_path / "report.json"
    payload = {"matched": False, "exact_bytes": 10, "total_bytes": 20, "matching_prefix_bytes": 7}

    record = normalize_external_report(repo, "unit.c", payload, report)

    assert record["adapter"] == "external"
    assert record["unit"] == "unit.c"
    assert record["score"] == payload
    assert record["external_report"] == str(report)


def test_watch_persists_report_hashes_across_invocations(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state_dir = tmp_path / "state"
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"matched": False, "exact_bytes": 10, "total_bytes": 20}), encoding="utf-8")

    run_watch(repo, "unit.c", report, state_dir, None, "Goal", 0, 1, True)
    run_watch(repo, "unit.c", report, state_dir, None, "Goal", 0, 1, True)

    lines = (state_dir / "watch-history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["external_report_sha256"]


def test_contributor_portal_explains_safe_agent_flow(tmp_path: Path) -> None:
    (tmp_path / "decomp-goal.toml").write_text(
        """
[project]
name = "portal-demo"
adapter = "generic"
default_unit = "attempt.c"

[commands]
score = "python score.py --candidate {unit} --json"
""".strip(),
        encoding="utf-8",
    )

    html = generate_contributor_portal(tmp_path, "Portal", 3, None)

    assert "Beginner Flow" in html
    assert "decomp-goal doctor" in html
    assert "decomp-goal goal" in html
    assert "Do not upload, fetch, or generate copyrighted original game input." in html


def test_apply_patch_set_reverts_earlier_patch_when_later_check_fails(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    good = tmp_path / "good.patch"
    good.write_text(
        """--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-one
+two
""",
        encoding="utf-8",
    )
    bad = tmp_path / "bad.patch"
    bad.write_text(
        """--- a/missing.txt
+++ b/missing.txt
@@ -1 +1 @@
-missing
+nope
""",
        encoding="utf-8",
    )

    applied, _ = apply_patch_set(repo, [good, bad])

    assert applied is False
    assert (repo / "file.txt").read_text(encoding="utf-8") == "one\n"
