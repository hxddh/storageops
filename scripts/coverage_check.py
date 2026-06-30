#!/usr/bin/env python3
"""Eval-corpus coverage floor.

The golden-case corpus is the capability regression gate; a baseline-enabled skill
with too few cases (or no reference baseline) is effectively untested. This gate
enforces a floor so coverage cannot silently erode:

  - every baseline-enabled category has at least MIN_CASES golden cases, and
  - every baseline-enabled category has at least one baseline-output reference.

Deterministic; reads the taxonomy, cases, and baseline-outputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "skills" / "storageops-eval-golden-cases"
CASES = CORPUS / "cases"
BASELINES = CORPUS / "baseline-outputs"
TAXONOMY = ROOT / "docs" / "skill-taxonomy.json"

MIN_CASES = 3  # per baseline-enabled category


def main() -> int:
    tax = json.loads(TAXONOMY.read_text(encoding="utf-8"))["categories"]
    baseline_cats = {c for c, e in tax.items() if e.get("baseline") is True}

    case_cat: dict[str, int] = {}
    baseline_cat: dict[str, int] = {}
    baselines = {p.stem for p in BASELINES.glob("*.md")}
    for case in sorted(CASES.iterdir()):
        ej = case / "expected.json"
        if not ej.exists():
            continue
        cat = json.loads(ej.read_text(encoding="utf-8")).get("expected_category")
        if cat is None:
            continue
        case_cat[cat] = case_cat.get(cat, 0) + 1
        if case.name in baselines:
            baseline_cat[cat] = baseline_cat.get(cat, 0) + 1

    errors: list[str] = []
    for cat in sorted(baseline_cats):
        n = case_cat.get(cat, 0)
        b = baseline_cat.get(cat, 0)
        if n < MIN_CASES:
            errors.append(f"category {cat}: only {n} golden case(s), need >= {MIN_CASES}")
        if b < 1:
            errors.append(f"category {cat}: {n} case(s) but no baseline-output reference")

    if errors:
        print("Coverage check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Coverage check passed: {len(baseline_cats)} baseline categories, "
          f"each >= {MIN_CASES} cases with a baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
