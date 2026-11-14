#!/usr/bin/env python3
"""Root-cause contract gate.

Verifies that one vocabulary is shared by the contract, the skills, the eval
corpus, and the generated extension table:

  * every golden case's expected root causes resolve inside its category's domain
  * every diagnostic SKILL.md declares exactly its domain's canonical ids
  * no alias resolves to two different ids inside one domain
  * the generated extension table matches the JSON contract
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "storageops-eval-golden-cases" / "lib"))

from gen_contract import OUT, render  # noqa: E402
from root_causes import build_index, load_contract, normalize  # noqa: E402

CASES = ROOT / "skills" / "storageops-eval-golden-cases" / "cases"


def check_cases(contract: dict, index: dict) -> list[str]:
    errors: list[str] = []
    for expected_path in sorted(CASES.glob("*/expected.json")):
        case = expected_path.parent.name
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        domain = expected.get("expected_category")
        terms = expected.get("expected_root_cause_types") or []
        if not terms:
            continue
        if domain not in contract["domains"]:
            errors.append(f"{case}: unknown expected_category {domain!r}")
            continue
        for term in terms:
            if normalize(term) not in index.get(domain, {}):
                errors.append(f"{case}: root cause {term!r} is not in contract domain {domain}")
    return errors


def _enum_ids(skill_md: Path) -> list[str] | None:
    match = re.search(r"root_cause_type=\[([^\]]+)\]", skill_md.read_text(encoding="utf-8"))
    if not match:
        return None
    return [part.strip() for part in match.group(1).split("|") if part.strip()]


def check_skills(contract: dict) -> list[str]:
    errors: list[str] = []
    for domain, spec in sorted(contract["domains"].items()):
        skill = spec["skill"]
        skill_md = ROOT / "skills" / skill / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"{domain}: missing {skill}/SKILL.md")
            continue
        declared = _enum_ids(skill_md)
        if declared is None:
            errors.append(f"{domain}: {skill}/SKILL.md has no root_cause_type=[...] contract line")
            continue
        want = [entry["id"] for entry in spec["root_causes"]]
        if sorted(set(declared)) != sorted(set(want)):
            missing = sorted(set(want) - set(declared))
            extra = sorted(set(declared) - set(want))
            errors.append(f"{domain}: {skill} enum mismatch (missing={missing}, extra={extra})")
        if len(declared) != len(set(declared)):
            errors.append(f"{domain}: {skill} enum has duplicate ids")
    return errors


def check_aliases(index: dict) -> list[str]:
    errors: list[str] = []
    for domain, terms in sorted(index.items()):
        seen: dict[str, str] = {}
        for term, canonical in terms.items():
            if term in seen and seen[term] != canonical:
                errors.append(f"{domain}: alias {term!r} maps to both {seen[term]} and {canonical}")
            seen[term] = canonical
    return errors


def check_generated(contract: dict) -> list[str]:
    if not OUT.exists():
        return [f"missing generated table {OUT.relative_to(ROOT)} (run make contract)"]
    if OUT.read_text(encoding="utf-8") != render(contract):
        return ["contract.generated.ts is stale (run make contract)"]
    return []


def main() -> int:
    contract = load_contract()
    index = build_index(contract)
    errors = (
        check_cases(contract, index)
        + check_skills(contract)
        + check_aliases(index)
        + check_generated(contract)
    )
    if errors:
        print("Root-cause contract check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    total = sum(len(spec["root_causes"]) for spec in contract["domains"].values())
    print(
        f"Root-cause contract check passed: {len(contract['domains'])} domains, {total} root causes, "
        f"v{contract['version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
