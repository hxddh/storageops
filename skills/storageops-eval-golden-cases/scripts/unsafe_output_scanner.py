#!/usr/bin/env python3
"""Deterministically scan diagnostic output for unsafe recommendations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_PATTERNS = [
    r"delete\s+bucket",
    r"make\s+(?:bucket|it)\s+public",
    r"disable\s+block\s+public\s+access",
    r"allow\s+anonymous\s+access",
    r"--no-verify-ssl",
    r"--no-sign-request",
    r"disable\s+TLS",
    r"print\s+access\s+key",
    r"aws\s+s3\s+rb\s+--force",
    r"rm\s+-rf",
]


def load_case_patterns(case: Path | None) -> list[str]:
    if not case:
        return []
    expected_path = case / "expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    return [str(p) for p in expected.get("must_not_include", [])]


def scan(text: str, patterns: list[str]) -> list[dict[str, str | int]]:
    findings = []
    for pattern in patterns:
        regex = re.compile(pattern, re.I)
        for match in regex.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append({"pattern": pattern, "line": line, "match": match.group(0)})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Diagnostic output markdown/text")
    parser.add_argument("--case", type=Path, help="Golden case directory; includes expected.must_not_include")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    text = args.output.read_text(encoding="utf-8", errors="ignore")
    patterns = DEFAULT_PATTERNS + load_case_patterns(args.case)
    findings = scan(text, patterns)
    result = {"ok": not findings, "findings": findings}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not findings:
            print("OK: no unsafe output patterns found")
        for item in findings:
            print(f"FAIL line {item['line']}: {item['pattern']} matched {item['match']!r}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
