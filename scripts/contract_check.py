#!/usr/bin/env python3
"""Output-Contract consistency gate.

The eval corpus grades reports by section headings (`Summary` / `Key Evidence` /
`Remediation` for diagnosis, `Routing` / `Evidence Gaps` for triage). For the
benchmark to measure what the skills actually instruct, every skill's Output
Contract must use that same canonical vocabulary. Before v0.7.0 each skill had its
own divergent headings (`Evidence`, `Recommendations`, `Fix`, ...), so a faithful
report could miss the graded sections. This gate locks the vocabulary.

Diagnostic skills must contain, as `##` headings in SKILL.md:
  Summary, Key Evidence, Remediation, What Would Falsify This, Risks / Open Questions
The router (triage) must contain: Routing, Evidence Gaps.
The reporting skill must contain: Summary, Key Evidence, Remediation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

DIAGNOSTIC_REQUIRED = [
    "Summary", "Key Evidence", "Remediation",
    "What Would Falsify This", "Risks / Open Questions",
]
SPECIAL = {
    "storageops-triage": ["Routing", "Evidence Gaps"],
    "storageops-evidence-reporting": ["Summary", "Key Evidence", "Remediation"],
}
EXEMPT = {"storageops-eval-golden-cases"}


def _headings(text: str) -> set[str]:
    return {m.strip() for m in re.findall(r"^#{1,4}\s+(.+?)\s*$", text, re.M)}


def main() -> int:
    errors: list[str] = []
    for skill_dir in sorted(SKILLS.glob("storageops-*")):
        name = skill_dir.name
        if name in EXEMPT:
            continue
        md = skill_dir / "SKILL.md"
        if not md.exists():
            continue
        headings = _headings(md.read_text(encoding="utf-8"))
        required = SPECIAL.get(name, DIAGNOSTIC_REQUIRED)
        missing = [s for s in required if s not in headings]
        if missing:
            errors.append(f"{name}/SKILL.md: Output Contract missing canonical section(s): {missing}")

    if errors:
        print("Output-Contract check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Output-Contract check passed: all skills use the canonical section vocabulary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
