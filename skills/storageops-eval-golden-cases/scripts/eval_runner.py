#!/usr/bin/env python3
"""Evaluate one diagnostic output against one StorageOps golden case."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def contains_all(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    return [kw for kw in keywords if kw.lower() not in lower]


def section_present(text: str, section: str) -> bool:
    pattern = rf"^#+\s*{re.escape(section)}\b"
    return re.search(pattern, text, re.I | re.M) is not None or section.lower() in text.lower()


def evaluate(case: Path, output: Path) -> dict:
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    text = output.read_text(encoding="utf-8", errors="ignore")
    lower = text.lower()

    failures = []
    warnings = []

    category = expected.get("expected_category")
    if category and category.lower() not in lower:
        failures.append(f"expected_category not found: {category}")

    for key in ["must_include_evidence_keywords", "must_include_recommendation_keywords"]:
        missing = contains_all(text, expected.get(key, []))
        if missing:
            failures.append(f"missing {key}: {missing}")

    forbidden = [kw for kw in expected.get("must_not_include", []) if kw.lower() in lower]
    if forbidden:
        failures.append(f"forbidden output present: {forbidden}")

    missing_sections = [s for s in expected.get("required_report_sections", []) if not section_present(text, s)]
    if missing_sections:
        warnings.append(f"missing report sections: {missing_sections}")

    should_missing = contains_all(text, expected.get("should_include_evidence_keywords", []))
    if should_missing:
        warnings.append(f"missing optional evidence keywords: {should_missing}")

    status = "PASS"
    if failures:
        status = "HARD_FAIL"
    elif warnings:
        status = "SOFT_FAIL"

    return {"case": case.name, "output": str(output), "status": status, "failures": failures, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path, help="Golden case directory")
    parser.add_argument("--output", required=True, type=Path, help="Diagnostic output file")
    args = parser.parse_args()
    result = evaluate(args.case, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"PASS", "SOFT_FAIL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
