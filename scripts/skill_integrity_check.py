#!/usr/bin/env python3
"""Validate StorageOps skill pack integrity.

Checks:
- Every skills/storageops-* directory has SKILL.md with required frontmatter.
- skill-registry.yaml paths exist and match SKILL.md metadata.
- All `references/...` and `scripts/...` links in SKILL.md exist.
- recommended_tools are registered by the TypeScript extension.
- Golden cases have valid expected.json and non-empty input artifacts.
- Repository size budgets keep golden cases compact.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
REGISTRY = ROOT / "skill-registry.yaml"
EXTENSION = ROOT / "storageops_cli" / "extensions" / "storageops.ts"
EVAL_CASES = SKILLS_DIR / "storageops-eval-golden-cases" / "cases"
TAXONOMY = ROOT / "docs" / "skill-taxonomy.json"
MAX_GOLDEN_INPUT_BYTES = 10 * 1024
MAX_GOLDEN_CASE_BYTES = 25 * 1024
MAX_GOLDEN_CASES_BYTES = 512 * 1024
MAX_TAXONOMY_BYTES = 20 * 1024
MAX_SKILL_MD_BYTES = 40 * 1024

REQUIRED_FRONTMATTER = {"name", "description", "maturity", "mode", "trigger_keywords", "recommended_tools"}
REQUIRED_EXPECTED = {
    "expected_category",
    "expected_min_confidence",
    "must_include_evidence_keywords",
    "must_include_recommendation_keywords",
    "must_not_include",
    "required_report_sections",
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def parse_frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    try:
        block = text.split("---", 2)[1]
    except IndexError as exc:
        raise ValueError("unterminated YAML frontmatter") from exc

    meta: dict[str, Any] = {}
    current: str | None = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current = key
            if value in {"", ">", "|"}:
                meta[key] = [] if value == "" else ""
            else:
                meta[key] = value.strip('"')
        elif current and line.lstrip().startswith("-"):
            value = line.lstrip()[1:].strip().strip('"')
            if not isinstance(meta.get(current), list):
                meta[current] = []
            meta[current].append(value)
        elif current and isinstance(meta.get(current), str):
            meta[current] = (str(meta[current]) + " " + line.strip()).strip()
    return meta


def parse_registry(path: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"  - name:\s*(\S+)", line)
        if m:
            current = {"name": m.group(1)}
            entries[current["name"]] = current
            continue
        if current:
            m = re.match(r"    (path|maturity|mode):\s*(.+?)\s*$", line)
            if m:
                current[m.group(1)] = m.group(2).strip().strip('"')
    return entries


def registered_tools() -> set[str]:
    text = EXTENSION.read_text(encoding="utf-8")
    return set(re.findall(r'name:\s*"([a-zA-Z0-9_-]+)"', text))


def load_taxonomy(errors: list[str]) -> dict[str, str]:
    if not TAXONOMY.exists():
        fail(errors, f"{TAXONOMY}: missing taxonomy file")
        return {}
    try:
        data = json.loads(TAXONOMY.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(errors, f"{TAXONOMY}: invalid JSON: {exc}")
        return {}
    categories = data.get("categories")
    if not isinstance(categories, dict) or not categories:
        fail(errors, f"{TAXONOMY}: categories must be a non-empty object")
        return {}
    mapping: dict[str, str] = {}
    for category, entry in categories.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("skill"), str):
            fail(errors, f"{TAXONOMY}: category {category!r} must define a skill")
            continue
        mapping[category] = entry["skill"]
    return mapping


def validate_skills(errors: list[str]) -> dict[str, dict[str, Any]]:
    tools = registered_tools()
    metas: dict[str, dict[str, Any]] = {}
    for skill_dir in sorted(SKILLS_DIR.glob("storageops-*")):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            fail(errors, f"{skill_dir}: missing SKILL.md")
            continue
        try:
            meta = parse_frontmatter(skill_file)
        except ValueError as exc:
            fail(errors, f"{skill_file}: {exc}")
            continue
        if skill_file.stat().st_size > MAX_SKILL_MD_BYTES:
            fail(errors, f"{skill_file}: exceeds {MAX_SKILL_MD_BYTES} byte SKILL.md budget")
        missing = REQUIRED_FRONTMATTER - set(meta)
        if missing:
            fail(errors, f"{skill_file}: missing frontmatter fields: {sorted(missing)}")
        name = str(meta.get("name", skill_dir.name))
        metas[name] = meta
        if name != skill_dir.name:
            fail(errors, f"{skill_file}: name '{name}' does not match directory '{skill_dir.name}'")

        recommended = meta.get("recommended_tools", [])
        if not isinstance(recommended, list) or not recommended:
            fail(errors, f"{skill_file}: recommended_tools must be a non-empty list")
        else:
            unknown = sorted(set(recommended) - tools)
            if unknown:
                fail(errors, f"{skill_file}: unknown recommended_tools: {unknown}")

        text = skill_file.read_text(encoding="utf-8")
        links = sorted(set(re.findall(r"`((?:references|scripts)/[^`]+?)`", text)))
        for link in links:
            if not (skill_dir / link).exists():
                fail(errors, f"{skill_file}: broken bundled-resource link `{link}`")

        # Every deterministic helper must be wired into the skill: a helper the
        # SKILL.md never names is one the agent will never run. This prevents
        # "built a helper, forgot to tell the agent to use it" regressions.
        for helper in sorted((skill_dir / "scripts").glob("*.py")):
            if helper.name not in text:
                fail(
                    errors,
                    f"{skill_file}: helper scripts/{helper.name} is not referenced in SKILL.md "
                    f"(the agent will never run it); wire it into the workflow",
                )
    return metas


def validate_registry(errors: list[str], metas: dict[str, dict[str, Any]]) -> None:
    registry = parse_registry(REGISTRY)
    skill_names = set(metas)
    registry_names = set(registry)
    for name in sorted(skill_names - registry_names):
        fail(errors, f"skill-registry.yaml: missing skill {name}")
    for name in sorted(registry_names - skill_names):
        fail(errors, f"skill-registry.yaml: unknown skill {name}")
    for name in sorted(skill_names & registry_names):
        entry = registry[name]
        path = ROOT / entry.get("path", "")
        if not path.exists():
            fail(errors, f"skill-registry.yaml: path for {name} does not exist: {entry.get('path')}")
        for field in ("maturity", "mode"):
            if str(metas[name].get(field)) != entry.get(field):
                fail(
                    errors,
                    f"skill-registry.yaml: {name}.{field} mismatch "
                    f"registry={entry.get(field)!r} skill={metas[name].get(field)!r}",
                )


def validate_taxonomy(errors: list[str], metas: dict[str, dict[str, Any]], category_to_skill: dict[str, str]) -> None:
    if TAXONOMY.exists() and TAXONOMY.stat().st_size > MAX_TAXONOMY_BYTES:
        fail(errors, f"{TAXONOMY}: exceeds {MAX_TAXONOMY_BYTES} byte taxonomy budget")
    for category, skill in sorted(category_to_skill.items()):
        if skill not in metas:
            fail(errors, f"{TAXONOMY}: category {category!r} maps to unknown skill {skill!r}")


def validate_golden_cases(errors: list[str], category_to_skill: dict[str, str]) -> None:
    if not EVAL_CASES.exists():
        return
    total_bytes = 0
    for case_dir in sorted(p for p in EVAL_CASES.iterdir() if p.is_dir()):
        case_bytes = sum(path.stat().st_size for path in case_dir.rglob("*") if path.is_file())
        total_bytes += case_bytes
        if case_bytes > MAX_GOLDEN_CASE_BYTES:
            fail(errors, f"{case_dir}: exceeds {MAX_GOLDEN_CASE_BYTES} byte golden-case budget")
        expected_path = case_dir / "expected.json"
        input_dir = case_dir / "input"
        if not expected_path.exists():
            fail(errors, f"{case_dir}: missing expected.json")
            continue
        if not input_dir.is_dir() or not any(input_dir.iterdir()):
            fail(errors, f"{case_dir}: missing or empty input/ directory")
        elif any(path.stat().st_size > MAX_GOLDEN_INPUT_BYTES for path in input_dir.rglob("*") if path.is_file()):
            fail(errors, f"{case_dir}: input artifact exceeds {MAX_GOLDEN_INPUT_BYTES} byte budget")
        try:
            expected = json.loads(expected_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(errors, f"{expected_path}: invalid JSON: {exc}")
            continue
        missing = REQUIRED_EXPECTED - set(expected)
        if missing:
            fail(errors, f"{expected_path}: missing fields: {sorted(missing)}")
        category = expected.get("expected_category")
        if not isinstance(category, str) or category not in category_to_skill:
            fail(errors, f"{expected_path}: expected_category must exist in docs/skill-taxonomy.json")
        confidence = expected.get("expected_min_confidence")
        if not isinstance(confidence, (int, float)) or not (0.5 <= float(confidence) <= 0.95):
            fail(errors, f"{expected_path}: expected_min_confidence must be between 0.5 and 0.95")
        must_not = expected.get("must_not_include")
        if not isinstance(must_not, list) or not must_not:
            fail(errors, f"{expected_path}: must_not_include must be a non-empty list")
    if total_bytes > MAX_GOLDEN_CASES_BYTES:
        fail(errors, f"{EVAL_CASES}: exceeds {MAX_GOLDEN_CASES_BYTES} byte total golden-cases budget")


def main() -> int:
    errors: list[str] = []
    metas = validate_skills(errors)
    validate_registry(errors, metas)
    category_to_skill = load_taxonomy(errors)
    validate_taxonomy(errors, metas, category_to_skill)
    validate_golden_cases(errors, category_to_skill)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"Skill integrity check failed: {len(errors)} issue(s)", file=sys.stderr)
        return 1
    print(f"Skill integrity check passed: {len(metas)} skills, {len(list(EVAL_CASES.glob('*'))) if EVAL_CASES.exists() else 0} golden cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
