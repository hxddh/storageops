#!/usr/bin/env python3
"""Validate StorageOps golden case definitions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = {
    "expected_category",
    "expected_min_confidence",
    "must_include_evidence_keywords",
    "must_include_recommendation_keywords",
    "must_not_include",
    "required_report_sections",
}
SECRET_PATTERNS = [
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----"),
    re.compile(r"Authorization\s*:\s*(?:Bearer|Basic|AWS4-HMAC-SHA256)\s+\S+", re.I),
]
EXAMPLE_SECRET_MARKERS = ("EXAMPLE", "example")

ROOT = Path(__file__).resolve().parents[3]
TAXONOMY = ROOT / "docs" / "skill-taxonomy.json"


def load_taxonomy() -> dict[str, str]:
    data = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    return {
        category: entry["skill"]
        for category, entry in data.get("categories", {}).items()
        if isinstance(entry, dict) and isinstance(entry.get("skill"), str)
    }


def iter_cases(root: Path):
    if (root / "expected.json").exists():
        yield root
    else:
        yield from sorted(p for p in root.iterdir() if p.is_dir() and (p / "expected.json").exists())


def validate_case(case: Path, category_to_skill: dict[str, str]) -> list[str]:
    errors: list[str] = []
    expected_path = case / "expected.json"
    input_dir = case / "input"
    try:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"{expected_path}: invalid JSON: {exc}"]

    missing = REQUIRED - set(expected)
    if missing:
        errors.append(f"{expected_path}: missing fields: {sorted(missing)}")

    category = expected.get("expected_category")
    if not isinstance(category, str) or category not in category_to_skill:
        errors.append(f"{expected_path}: expected_category must exist in docs/skill-taxonomy.json")

    confidence = expected.get("expected_min_confidence")
    if not isinstance(confidence, (int, float)) or not 0.5 <= float(confidence) <= 0.95:
        errors.append(f"{expected_path}: expected_min_confidence must be 0.5..0.95")

    for key in ["must_include_evidence_keywords", "must_include_recommendation_keywords", "must_not_include", "required_report_sections"]:
        if not isinstance(expected.get(key), list) or not expected.get(key):
            errors.append(f"{expected_path}: {key} must be a non-empty list")

    # Optional, but when present it is consumed by eval_runner, so enforce shape.
    if "expected_root_cause_types" in expected:
        value = expected["expected_root_cause_types"]
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            errors.append(f"{expected_path}: expected_root_cause_types must be a non-empty list of strings")

    if not input_dir.is_dir() or not any(input_dir.iterdir()):
        errors.append(f"{case}: input/ must contain at least one artifact")
    else:
        for artifact in input_dir.rglob("*"):
            if artifact.is_file():
                text = artifact.read_text(encoding="utf-8", errors="ignore")
                # AWS documentation-style sample credentials include EXAMPLE inside
                # the credential-shaped token itself. Do not allow unrelated nearby
                # prose to whitelist a real-looking secret.
                for pattern in SECRET_PATTERNS:
                    for match in pattern.finditer(text):
                        token = match.group(0)
                        if any(marker in token for marker in EXAMPLE_SECRET_MARKERS):
                            continue
                        errors.append(f"{artifact}: possible unredacted secret matches {pattern.pattern}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="A case directory or cases/ root")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    try:
        category_to_skill = load_taxonomy()
    except Exception as exc:
        print(f"FAIL: {TAXONOMY}: cannot load taxonomy: {exc}", file=sys.stderr)
        return 1

    report = []
    for case in iter_cases(args.path):
        errors = validate_case(case, category_to_skill)
        report.append({"case": str(case), "ok": not errors, "errors": errors})

    ok = all(item["ok"] for item in report)
    if args.json:
        print(json.dumps({"ok": ok, "cases": report}, indent=2, ensure_ascii=False))
    else:
        for item in report:
            status = "OK" if item["ok"] else "FAIL"
            print(f"{status}: {item['case']}")
            for error in item["errors"]:
                print(f"  - {error}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
