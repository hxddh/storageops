#!/usr/bin/env python3
"""Require scope and verification notes for tool-specific reference docs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_REFS = ROOT / "skills" / "storageops-cli-sdk-diagnosis" / "references"

REQUIRED_SECTIONS = ("## Scope", "## Verify Before Applying")
DENYLISTED_FACTS = {
    "~/.bce/credentials": "BOS CMD defaults to ~/.go-bcecli/credentials; BCE SDKs have their own config patterns.",
    "~/.bce/config": "BOS CMD defaults to ~/.go-bcecli/config; BCE SDKs have their own config patterns.",
}


def main() -> int:
    errors: list[str] = []
    for path in sorted(CLI_REFS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        missing = [section for section in REQUIRED_SECTIONS if section not in text]
        if missing:
            errors.append(f"{path.relative_to(ROOT)}: missing {', '.join(missing)}")

    for path in sorted((ROOT / "skills").rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for fact, reason in DENYLISTED_FACTS.items():
            if fact in text:
                errors.append(f"{path.relative_to(ROOT)}: denylisted reference fact {fact!r}: {reason}")

    if errors:
        print("Reference scope check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "Tool/SDK references must state their scope and how to verify local facts before applying them.",
            file=sys.stderr,
        )
        return 1

    print("Reference scope check passed: CLI/SDK references include scope and verification notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
