#!/usr/bin/env python3
"""Evaluate many StorageOps golden-case outputs and emit one JSON summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from eval_runner import evaluate, load_expected_category, summarize_results  # noqa: E402


def iter_cases(cases_root: Path):
    if (cases_root / "expected.json").exists():
        yield cases_root
        return
    yield from sorted(p for p in cases_root.iterdir() if p.is_dir() and (p / "expected.json").exists())


def find_output(outputs_root: Path, case_name: str, suffix: str) -> Path:
    return outputs_root / f"{case_name}{suffix}"


def missing_result(case: Path, output: Path) -> dict:
    return {
        "case": case.name,
        "expected_category": load_expected_category(case),
        "output": str(output),
        "status": "MISSING",
        "failures": [f"missing output file: {output}"],
        "warnings": [],
    }


def evaluate_all(cases_root: Path, outputs_root: Path, suffix: str, only_with_outputs: bool = False) -> dict:
    results = []
    for case in iter_cases(cases_root):
        output = find_output(outputs_root, case.name, suffix)
        if not output.exists():
            if only_with_outputs:
                continue
            results.append(missing_result(case, output))
            continue
        result = evaluate(case, output)
        result["expected_category"] = load_expected_category(case)
        results.append(result)

    return {"summary": summarize_results(results), "results": results}


def print_text_report(report: dict) -> None:
    summary = report["summary"]
    counts = summary["counts"]
    print(
        "Eval summary: "
        f"{counts.get('PASS', 0)} PASS, "
        f"{counts.get('SOFT_FAIL', 0)} SOFT_FAIL, "
        f"{counts.get('HARD_FAIL', 0)} HARD_FAIL, "
        f"{counts.get('MISSING', 0)} MISSING "
        f"({summary['pass_rate']:.1%} pass rate)"
    )
    for item in report["results"]:
        if item["status"] in {"HARD_FAIL", "MISSING"}:
            print(f"- {item['case']}: {item['status']} — {'; '.join(item['failures'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path, help="Golden cases root or one case directory")
    parser.add_argument("--outputs", required=True, type=Path, help="Directory containing <case>.md outputs")
    parser.add_argument("--suffix", default=".md", help="Output filename suffix; default: .md")
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    parser.add_argument("--only-with-outputs", action="store_true", help="Evaluate only cases with matching output files")
    parser.add_argument("--quiet", action="store_true", help="Only print JSON or write json-out")
    args = parser.parse_args()

    report = evaluate_all(args.cases, args.outputs, args.suffix, args.only_with_outputs)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    elif args.quiet:
        print(text)
    if not args.quiet:
        print_text_report(report)
    return 0 if not report["summary"]["counts"].get("HARD_FAIL") and not report["summary"]["counts"].get("MISSING") else 1


if __name__ == "__main__":
    raise SystemExit(main())
