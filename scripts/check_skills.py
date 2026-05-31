#!/usr/bin/env python3
"""Validate StorageOps skill metadata and registry consistency."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "agents" / "skills"
REGISTRY = ROOT / "skill-registry.yaml"
NAME_RE = re.compile(r"^[a-z0-9-]+$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)
MERGE_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
DANGEROUS_PHRASES = [
    re.compile(r"(?i)read\s+(?:real\s+)?(?:aws\s+)?credential\s+files?"),
    re.compile(r"(?i)automatically\s+(?:delete|put|post|modify|change)"),
    re.compile(r"(?i)execute\s+(?:delete|put|post).{0,40}(?:bucket|object|policy)"),
    re.compile(r"(?i)delete\s+buckets?\s+automatically"),
]


def parse_frontmatter(text: str) -> dict[str, str] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    fields: dict[str, str] = {}
    current_key: str | None = None
    parts: list[str] = []
    for raw in match.group(1).splitlines():
        if not raw.strip():
            continue
        if not raw.startswith((" ", "\t")) and ":" in raw:
            if current_key is not None:
                fields[current_key] = "\n".join(parts).strip().strip('"\'')
            key, _, value = raw.partition(":")
            current_key = key.strip()
            value = value.strip()
            parts = [] if value in {">", "|"} else [value]
        elif current_key is not None:
            parts.append(raw.strip())
    if current_key is not None:
        fields[current_key] = "\n".join(parts).strip().strip('"\'')
    return fields


def registry_skill_names() -> set[str]:
    if not REGISTRY.exists():
        return set()
    text = REGISTRY.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*-\s+name:\s*([a-z0-9-]+)\s*$", text, re.MULTILINE))


def main() -> int:
    errors: list[str] = []
    if not SKILLS_DIR.exists():
        errors.append(f"missing skills directory: {SKILLS_DIR}")
    skill_dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()) if SKILLS_DIR.exists() else []
    skill_names: set[str] = set()

    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            errors.append(f"missing SKILL.md: {skill_dir.relative_to(ROOT)}")
            continue
        text = skill_file.read_text(encoding="utf-8", errors="replace")
        rel = skill_file.relative_to(ROOT)
        if any(marker in text for marker in MERGE_MARKERS):
            errors.append(f"merge conflict marker found: {rel}")
        for line in text.splitlines():
            lower = line.lower()
            if "do not" in lower or "never" in lower or "禁止" in line:
                continue
            for pattern in DANGEROUS_PHRASES:
                if pattern.search(line):
                    errors.append(f"dangerous phrase found in {rel}: {pattern.pattern}")
        fm = parse_frontmatter(text)
        if fm is None:
            errors.append(f"missing or invalid YAML frontmatter: {rel}")
            continue
        name = fm.get("name", "").strip()
        description = fm.get("description", "").strip()
        if not name:
            errors.append(f"missing name: {rel}")
        elif not NAME_RE.fullmatch(name):
            errors.append(f"invalid name {name!r}: {rel}")
        else:
            skill_names.add(name)
            if name != skill_dir.name:
                errors.append(f"frontmatter name/path mismatch: {rel} declares {name!r}")
        if not description:
            errors.append(f"missing description: {rel}")
        elif len(description.split()) < 8:
            errors.append(f"description is not specific enough: {rel}")

    registry_names = registry_skill_names()
    if not registry_names:
        errors.append("skill-registry.yaml has no parsable skill entries")
    missing_in_registry = skill_names - registry_names
    missing_on_disk = registry_names - skill_names
    for name in sorted(missing_in_registry):
        errors.append(f"skill missing from registry: {name}")
    for name in sorted(missing_on_disk):
        errors.append(f"registry entry missing matching SKILL.md: {name}")

    if errors:
        print("Skill validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"OK: {len(skill_names)} skills validated and matched skill-registry.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
