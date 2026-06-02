#!/usr/bin/env python3
"""Evaluate one diagnostic output against one StorageOps golden case."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TAXONOMY = ROOT / "docs" / "skill-taxonomy.json"
STATUS_RANK = {"PASS": 2, "SOFT_FAIL": 1, "HARD_FAIL": 0, "MISSING": -1}


def load_taxonomy() -> dict[str, str]:
    if not TAXONOMY.exists():
        return {}
    data = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    return {
        category: entry["skill"]
        for category, entry in data.get("categories", {}).items()
        if isinstance(entry, dict) and isinstance(entry.get("skill"), str)
    }


def contains_all(text: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if not keyword_present(text, kw)]


def parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Za-z][A-Za-z _-]{0,40})\s*:\s*(.+?)\s*$", line)
        if match:
            key = match.group(1).strip().lower().replace(" ", "_").replace("-", "_")
            fields[key] = match.group(2).strip()
    return fields


def has_cjk(value: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in value)


def keyword_present(text: str, keyword: str) -> bool:
    if not keyword:
        return True
    if has_cjk(keyword):
        return keyword.lower() in text.lower()
    escaped = re.escape(keyword)
    if re.fullmatch(r"[A-Za-z0-9_]+", keyword):
        pattern = rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
    else:
        pattern = escaped
    return re.search(pattern, text, re.I) is not None


def forbidden_hits(text: str, keywords: list[str]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for keyword in keywords:
        for match in keyword_matches(text, keyword):
            context = text[max(0, match.start() - 48): match.end() + 48]
            if safe_negation_context(context, keyword):
                continue
            hits.append({"keyword": keyword, "context": " ".join(context.split())})
    return hits


def keyword_matches(text: str, keyword: str) -> list[re.Match[str]]:
    if not keyword:
        return []
    escaped = re.escape(keyword)
    if has_cjk(keyword):
        pattern = escaped
    elif re.fullmatch(r"[A-Za-z0-9_]+", keyword):
        pattern = rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
    else:
        pattern = escaped
    return list(re.finditer(pattern, text, re.I))


def safe_negation_context(context: str, keyword: str) -> bool:
    lower = context.lower()
    keyword_lower = keyword.lower()
    index = lower.find(keyword_lower)
    if index < 0:
        return False
    before = lower[max(0, index - 32):index]
    safe_patterns = [
        "do not ",
        "don't ",
        "avoid ",
        "never ",
        "must not ",
        "should not ",
        "not recommend ",
        "do not use ",
        "do not run ",
    ]
    return any(pattern in before for pattern in safe_patterns)


def section_present(text: str, section: str) -> bool:
    pattern = rf"^#+\s*{re.escape(section)}\b"
    return re.search(pattern, text, re.I | re.M) is not None or section.lower() in text.lower()


def extract_confidence(text: str) -> float | None:
    patterns = [
        r'"confidence"\s*:\s*(0(?:\.\d+)?|1(?:\.0+)?)',
        r"\bconfidence\b\s*[:=]\s*(0(?:\.\d+)?|1(?:\.0+)?)",
        r"\bconfidence\b\s*[:=]\s*([1-9]\d?)%",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = float(match.group(1))
        return value / 100 if value > 1 else value
    return None


def category_or_route_present(text: str, category: str | None, mapped_skill: str) -> bool:
    if not category:
        return True
    fields = parse_fields(text)
    category_field = fields.get("category", "")
    route_field = fields.get("route", "")
    if category_field:
        normalized = category_field.lower()
        return normalized in {category.lower(), mapped_skill.lower()}
    if route_field and mapped_skill:
        return mapped_skill.lower() in route_field.lower()
    lower = text.lower()
    return category.lower() in lower or (bool(mapped_skill) and mapped_skill.lower() in lower)


def root_cause_type_present(text: str, root_cause_types: list[str]) -> bool:
    if not root_cause_types:
        return True
    fields = parse_fields(text)
    field_values = [
        fields.get("root_cause_type", ""),
        fields.get("root_cause", ""),
        fields.get("primary_diagnosis", ""),
    ]
    normalized_values = " ".join(field_values).lower()
    if any(keyword_present(normalized_values, root_cause) for root_cause in root_cause_types):
        return True
    return any(keyword_present(text, root_cause) for root_cause in root_cause_types)


def evaluate(case: Path, output: Path) -> dict:
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    category_to_skill = load_taxonomy()
    text = output.read_text(encoding="utf-8", errors="ignore")

    failures = []
    warnings = []

    category = expected.get("expected_category")
    mapped_skill = category_to_skill.get(category, "")
    if not category_or_route_present(text, category, mapped_skill):
        failures.append(f"expected_category or mapped skill not found: {category} -> {mapped_skill}")

    expected_confidence = expected.get("expected_min_confidence")
    if isinstance(expected_confidence, (int, float)):
        actual_confidence = extract_confidence(text)
        if actual_confidence is None:
            failures.append(f"confidence not found; expected >= {expected_confidence}")
        elif actual_confidence < float(expected_confidence):
            failures.append(f"confidence too low: {actual_confidence} < {expected_confidence}")

    for key in ["must_include_evidence_keywords", "must_include_recommendation_keywords"]:
        missing = contains_all(text, expected.get(key, []))
        if missing:
            failures.append(f"missing {key}: {missing}")

    root_cause_types = expected.get("expected_root_cause_types", [])
    if isinstance(root_cause_types, list) and root_cause_types:
        typed_root_causes = [str(item) for item in root_cause_types if isinstance(item, str)]
        if typed_root_causes and not root_cause_type_present(text, typed_root_causes):
            failures.append(f"expected_root_cause_types not found: {typed_root_causes}")

    forbidden = forbidden_hits(text, expected.get("must_not_include", []))
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


def summarize_results(results: list[dict]) -> dict:
    counts = {"PASS": 0, "SOFT_FAIL": 0, "HARD_FAIL": 0, "MISSING": 0}
    by_category: dict[str, dict[str, int]] = {}
    for item in results:
        status = str(item.get("status", "HARD_FAIL"))
        counts[status] = counts.get(status, 0) + 1
        category = str(item.get("expected_category", "unknown"))
        category_counts = by_category.setdefault(category, {"PASS": 0, "SOFT_FAIL": 0, "HARD_FAIL": 0, "MISSING": 0})
        category_counts[status] = category_counts.get(status, 0) + 1
    total = len(results)
    passing = counts.get("PASS", 0) + counts.get("SOFT_FAIL", 0)
    pass_rate = passing / total if total else 0.0
    return {"total": total, "counts": counts, "pass_rate": pass_rate, "by_category": by_category}


def load_expected_category(case: Path) -> str:
    expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
    return str(expected.get("expected_category", "unknown"))


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
