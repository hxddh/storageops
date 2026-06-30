#!/usr/bin/env python3
"""Validate StorageOps routing contract alignment across taxonomy assets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "docs" / "skill-taxonomy.json"
REGISTRY = ROOT / "skill-registry.yaml"
CASES = ROOT / "skills" / "storageops-eval-golden-cases" / "cases"
BASELINES = ROOT / "skills" / "storageops-eval-golden-cases" / "baseline-outputs"
EXTENSION_DIR = ROOT / "storageops_cli" / "extensions"


def extension_source_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(EXTENSION_DIR.glob("*.ts"))
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def registry_skill_names() -> set[str]:
    text = REGISTRY.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*-\s+name:\s+([a-z0-9-]+)\s*$", text, re.M))


def case_categories() -> dict[str, str]:
    categories: dict[str, str] = {}
    for expected in sorted(CASES.glob("*/expected.json")):
        data = load_json(expected)
        category = data.get("expected_category")
        if isinstance(category, str):
            categories[expected.parent.name] = category
    return categories


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def validate_taxonomy(taxonomy: dict, registry_names: set[str]) -> list[str]:
    errors: list[str] = []
    categories = taxonomy.get("categories", {})
    if not isinstance(categories, dict) or not categories:
        return ["taxonomy must contain categories"]

    for category, entry in sorted(categories.items()):
        if not isinstance(entry, dict):
            errors.append(f"{category}: entry must be an object")
            continue
        skill = entry.get("skill")
        if not isinstance(skill, str) or skill not in registry_names:
            errors.append(f"{category}: skill not found in registry: {skill}")
        for key in ["domains", "aliases", "signatures"]:
            value = entry.get(key)
            if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                errors.append(f"{category}: {key} must be a non-empty list of strings")
        if not isinstance(entry.get("baseline"), bool):
            errors.append(f"{category}: baseline must be boolean")
    return errors


def validate_cases(taxonomy: dict, cases: dict[str, str]) -> list[str]:
    categories = taxonomy.get("categories", {})
    errors = []
    for case, category in sorted(cases.items()):
        if category not in categories:
            errors.append(f"{case}: expected_category not in taxonomy: {category}")
    return errors


def validate_baselines(taxonomy: dict, cases: dict[str, str]) -> list[str]:
    categories = taxonomy.get("categories", {})
    errors = []
    for output in sorted(BASELINES.glob("*.md")):
        case = output.stem
        category = cases.get(case)
        if category is None:
            errors.append(f"{output.relative_to(ROOT)}: no matching golden case")
            continue
        entry = categories.get(category)
        if not isinstance(entry, dict):
            errors.append(f"{case}: baseline category not in taxonomy: {category}")
            continue
        if entry.get("baseline") is not True:
            errors.append(f"{case}: category {category} is not baseline-enabled")
    return errors


def validate_extension_coverage(taxonomy: dict) -> list[str]:
    text = extension_source_text()
    compact_extension = normalize(text)
    errors = []
    for category, entry in sorted(taxonomy.get("categories", {}).items()):
        if entry.get("baseline") is not True:
            continue
        skill = entry.get("skill", "")
        signatures = entry.get("signatures", [])
        if isinstance(skill, str) and skill not in text:
            errors.append(f"{category}: baseline skill missing from detect_domain extension: {skill}")
        if isinstance(signatures, list):
            if not any(normalize(sig) in compact_extension for sig in signatures if isinstance(sig, str)):
                errors.append(f"{category}: no baseline signature appears in detect_domain extension")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    try:
        taxonomy = load_json(TAXONOMY)
    except Exception as exc:
        print(f"FAIL: cannot load {TAXONOMY}: {exc}", file=sys.stderr)
        return 1

    registry_names = registry_skill_names()
    cases = case_categories()
    errors = []
    errors.extend(validate_taxonomy(taxonomy, registry_names))
    errors.extend(validate_cases(taxonomy, cases))
    errors.extend(validate_baselines(taxonomy, cases))
    errors.extend(validate_extension_coverage(taxonomy))

    if errors:
        print("Routing contract check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    baseline_count = len(list(BASELINES.glob("*.md")))
    print(
        "Routing contract check passed: "
        f"{len(taxonomy.get('categories', {}))} categories, "
        f"{len(cases)} cases, {baseline_count} baseline outputs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
