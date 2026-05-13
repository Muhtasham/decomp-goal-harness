#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import filecmp
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
ORIGINAL = ROOT / "original.c"


def cc() -> str:
    compiler = shutil.which("cc")
    if compiler is None:
        raise SystemExit("cc not found")
    return compiler


def compile_obj(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            cc(),
            "-O2",
            "-g0",
            "-fno-asynchronous-unwind-tables",
            "-c",
            str(source),
            "-o",
            str(output),
        ],
        check=True,
    )


def disassemble(path: Path) -> list[str]:
    objdump = shutil.which("objdump")
    if objdump is None:
        return []
    proc = subprocess.run([objdump, "-d", str(path)], text=True, capture_output=True, check=True)
    lines = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        if "file format" in line:
            continue
        lines.append(line)
    return lines


def build(candidate: Path) -> tuple[Path, Path]:
    original_obj = BUILD / "original.o"
    digest = hashlib.sha256(str(candidate).encode("utf-8")).hexdigest()[:12]
    candidate_obj = BUILD / f"candidate-{digest}.o"
    compile_obj(ORIGINAL, original_obj)
    compile_obj(candidate, candidate_obj)
    return original_obj, candidate_obj


def score(candidate: Path) -> dict[str, object]:
    original_obj, candidate_obj = build(candidate)
    original_bytes = original_obj.read_bytes()
    candidate_bytes = candidate_obj.read_bytes()
    total = max(len(original_bytes), len(candidate_bytes))
    exact = sum(
        1
        for i in range(total)
        if i < len(original_bytes)
        and i < len(candidate_bytes)
        and original_bytes[i] == candidate_bytes[i]
    )
    matched = filecmp.cmp(original_obj, candidate_obj, shallow=False)
    fuzzy = exact / total if total else 1.0
    return {
        "matched": matched,
        "score": round(fuzzy, 6),
        "exact_bytes": exact,
        "total_bytes": total,
        "original": str(original_obj),
        "candidate": str(candidate_obj),
    }


def diff(candidate: Path) -> str:
    original_obj, candidate_obj = build(candidate)
    original = disassemble(original_obj)
    candidate_lines = disassemble(candidate_obj)
    if not original or not candidate_lines:
        return "objdump not available"
    return "\n".join(
        difflib.unified_diff(
            original,
            candidate_lines,
            fromfile="original.o",
            tofile="candidate.o",
            lineterm="",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", default="attempt.c")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--diff", action="store_true")
    args = parser.parse_args()

    candidate = (ROOT / args.candidate).resolve()
    if not candidate.exists():
        print(f"candidate not found: {candidate}", file=sys.stderr)
        return 2

    if args.build_only:
        build(candidate)
        return 0
    if args.json:
        print(json.dumps(score(candidate), indent=2))
        return 0
    if args.diff:
        print(diff(candidate))
        return 0

    result = score(candidate)
    print(json.dumps(result, indent=2))
    return 0 if result["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
