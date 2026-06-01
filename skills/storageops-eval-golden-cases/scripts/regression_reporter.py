#!/usr/bin/env python3
"""Compare two eval result JSON files and report regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RANK = {"PASS": 2, "SOFT_FAIL": 1, "HARD_FAIL": 0}


def load_results(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "results" in data:
        items = data["results"]
    elif isinstance(data, list):
        items = data
    else:
        items = [data]
    return {str(item["case"]): str(item["status"]) for item in items}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    args = parser.parse_args()

    baseline = load_results(args.baseline)
    current = load_results(args.current)
    regressions = []
    improvements = []
    for case, old in sorted(baseline.items()):
        new = current.get(case, "MISSING")
        if new == "MISSING" or RANK.get(new, -1) < RANK.get(old, -1):
            regressions.append({"case": case, "baseline": old, "current": new})
        elif RANK.get(new, -1) > RANK.get(old, -1):
            improvements.append({"case": case, "baseline": old, "current": new})

    result = {"ok": not regressions, "regressions": regressions, "improvements": improvements}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not regressions else 1


if __name__ == "__main__":
    raise SystemExit(main())
