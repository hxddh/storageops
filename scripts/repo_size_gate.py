#!/usr/bin/env python3
"""Keep committed fixtures, golden cases, and generated artifacts small."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".whl",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
}
FORBIDDEN_PARTS = {"__pycache__", "build", "dist", ".pytest_cache"}

GOLDEN_FILE_LIMIT = 8 * 1024
GOLDEN_CASE_LIMIT = 20 * 1024
GOLDEN_CORPUS_LIMIT = 300 * 1024
BASELINE_FILE_LIMIT = 8 * 1024
BASELINE_CORPUS_LIMIT = 80 * 1024
TEST_FILE_LIMIT = 16 * 1024
TRACKED_TOTAL_LIMIT = 2 * 1024 * 1024

GOLDEN_ROOT = Path("skills/storageops-eval-golden-cases/cases")
BASELINE_ROOT = Path("skills/storageops-eval-golden-cases/baseline-outputs")


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line]


def file_size(path: Path) -> int:
    return (ROOT / path).stat().st_size


def case_name(path: Path) -> str | None:
    try:
        rel = path.relative_to(GOLDEN_ROOT)
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Reserved for future machine output")
    parser.parse_args()

    files = tracked_files()
    errors: list[str] = []
    golden_total = 0
    baseline_total = 0
    tracked_total = 0
    case_totals: dict[str, int] = {}

    for path in files:
        size = file_size(path)
        tracked_total += size
        parts = set(path.parts)

        if path.suffix in FORBIDDEN_SUFFIXES or parts & FORBIDDEN_PARTS:
            errors.append(f"forbidden generated/binary artifact tracked: {path}")

        if path.is_relative_to(GOLDEN_ROOT):
            golden_total += size
            if size > GOLDEN_FILE_LIMIT:
                errors.append(f"golden case file too large ({size} bytes > {GOLDEN_FILE_LIMIT}): {path}")
            name = case_name(path)
            if name:
                case_totals[name] = case_totals.get(name, 0) + size

        if path.is_relative_to(BASELINE_ROOT):
            baseline_total += size
            if size > BASELINE_FILE_LIMIT:
                errors.append(f"baseline output too large ({size} bytes > {BASELINE_FILE_LIMIT}): {path}")

        if path.parts and path.parts[0] == "tests" and size > TEST_FILE_LIMIT:
            errors.append(f"test file too large ({size} bytes > {TEST_FILE_LIMIT}): {path}")

    for name, size in sorted(case_totals.items()):
        if size > GOLDEN_CASE_LIMIT:
            errors.append(f"golden case too large ({size} bytes > {GOLDEN_CASE_LIMIT}): {name}")

    if golden_total > GOLDEN_CORPUS_LIMIT:
        errors.append(f"golden corpus too large ({golden_total} bytes > {GOLDEN_CORPUS_LIMIT})")
    if baseline_total > BASELINE_CORPUS_LIMIT:
        errors.append(f"baseline corpus too large ({baseline_total} bytes > {BASELINE_CORPUS_LIMIT})")
    if tracked_total > TRACKED_TOTAL_LIMIT:
        errors.append(f"tracked repository files too large ({tracked_total} bytes > {TRACKED_TOTAL_LIMIT})")

    if errors:
        print("Repo size gate failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(
        "Repo size gate passed: "
        f"tracked={tracked_total} bytes, golden={golden_total} bytes, "
        f"baseline={baseline_total} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
