#!/usr/bin/env python3
"""Reject volatile pricing literals in runtime SKILL.md instructions."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"

PRICE_PATTERNS = [
    re.compile(r"[$¥]\s*\d+(?:\.\d+)?"),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:USD|CNY|RMB)\b", re.I),
]


def main() -> int:
    errors: list[str] = []
    for path in sorted(SKILLS.glob("storageops-*/SKILL.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(pattern.search(line) for pattern in PRICE_PATTERNS):
                errors.append(f"{path.relative_to(ROOT)}:{lineno}: volatile pricing literal: {line.strip()}")

    if errors:
        print("Hardcoded pricing check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "Move concrete prices into dated references and keep SKILL.md focused on method.",
            file=sys.stderr,
        )
        return 1

    print("Hardcoded pricing check passed: no volatile pricing literals in SKILL.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
