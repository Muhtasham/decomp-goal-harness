from __future__ import annotations

from pathlib import Path

from decomp_goal.cli import (
    build_gap_report,
    dtk_progress_matched,
    extract_metrics,
    parse_dtk_progress,
    repo_relative_or_default,
    run_generic,
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
