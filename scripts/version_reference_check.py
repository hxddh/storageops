#!/usr/bin/env python3
"""Check that the version is consistent across canonical files.

pyproject.toml is the source of truth. Every release bumps the version in several
places; this gate fails fast when one is left behind, instead of relying on a
manual checklist.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (relative path, regex capturing the version, human label)
CHECKS = [
    ("skill-registry.yaml", r"^# StorageOps Skill Registry v(\d+\.\d+\.\d+)", "registry header"),
    ("docs/ARCHITECTURE.md", r"StorageOps v(\d+\.\d+\.\d+) is a Pi", "architecture intro"),
    ("docs/cli-reference.md", r"StorageOps v(\d+\.\d+\.\d+)\s+\(pi:", "cli-reference --version"),
    ("CHANGELOG.md", r"^##\s+.*\bv(\d+\.\d+\.\d+)\b", "changelog latest entry"),
]


def _first_match(path: Path, pattern: str) -> str | None:
    rx = re.compile(pattern, re.MULTILINE)
    m = rx.search(path.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def main() -> int:
    pyproject = ROOT / "pyproject.toml"
    canonical = _first_match(pyproject, r'^version = "(\d+\.\d+\.\d+)"')
    if not canonical:
        print("FAIL: could not read version from pyproject.toml", file=sys.stderr)
        return 1

    errors: list[str] = []
    for rel, pattern, label in CHECKS:
        path = ROOT / rel
        if not path.exists():
            errors.append(f"{rel}: missing file ({label})")
            continue
        found = _first_match(path, pattern)
        if found is None:
            errors.append(f"{rel}: no version reference found ({label})")
        elif found != canonical:
            errors.append(f"{rel}: {label} is v{found}, expected v{canonical}")

    if errors:
        print("Version reference check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"Version reference check passed: all canonical files at v{canonical}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
