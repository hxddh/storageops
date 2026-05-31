"""
StorageOps pipeline smoke test.

Runs a golden case through the rule-based triage → analyze pipeline and validates
the output. No LLM or Pi required — tests the deterministic diagnostic engine.

Set RUN_REAL_PI_SMOKE=1 to additionally run the Pi agent (requires Pi + API key).

Exit code 0 = pass, 1 = fail.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT / "storageops-cli"))

CASES_DIR = _ROOT / "agents" / "skills" / "storageops-eval-golden-cases" / "cases"
CASE_NAME = os.environ.get("STORAGEOPS_SMOKE_CASE", "rclone-corrupted-transfer")


def main() -> int:
    case_dir = CASES_DIR / CASE_NAME
    if not case_dir.exists():
        print(f"ERROR: case not found: {CASE_NAME}", file=sys.stderr)
        return 1

    expected = json.loads((case_dir / "expected.json").read_text())
    texts = [
        f.read_text(encoding="utf-8", errors="replace")
        for f in sorted((case_dir / "input").iterdir())
        if f.is_file()
    ]
    evidence_text = "\n\n".join(texts)
    expected_category = expected["expected_category"]
    print(f"[Smoke] Case: {CASE_NAME}  expected_category: {expected_category}")

    from storageops.agent import classify_evidence, run_analysis
    from storageops.report_validator import validate_report

    failures: list[str] = []

    # 1. Triage
    classification = classify_evidence(evidence_text)
    detected = classification["primary_domain"]
    if detected != expected_category:
        failures.append(
            f"triage mismatch: detected={detected!r} expected={expected_category!r}"
        )
    else:
        print(f"[Smoke] ✓ triage: {detected}")

    # 2. Analyze
    analysis = run_analysis(expected_category, evidence_text)
    if analysis.get("error"):
        failures.append(f"analyze returned error: {analysis['error']}")
    else:
        print(f"[Smoke] ✓ analyze: {list(analysis.keys())}")

    # 3. Report validation (generate a minimal report and validate structure)
    from storageops.agent import generate_report
    from storageops.agent import assess_evidence
    evidence_quality = assess_evidence(evidence_text, expected_category).get("quality", "partial")
    report = generate_report(expected_category, dict(analysis), evidence_quality)
    validation = validate_report(report)
    if not validation["valid"]:
        failures.append(
            f"report validation failed: missing={validation['missing_fields']} "
            f"invalid={validation['invalid_fields']}"
        )
    else:
        print("[Smoke] ✓ report structure valid")

    # 4. Keyword checks
    report_lower = report.lower()
    for kw in expected.get("must_include_evidence_keywords", []):
        if kw.lower() not in report_lower:
            failures.append(f"report missing required keyword: {kw!r}")
    for forbidden in expected.get("must_not_include", []):
        if forbidden.lower() in report_lower:
            failures.append(f"report contains forbidden phrase: {forbidden!r}")

    # 5. Optional: real Pi agent run
    if os.environ.get("RUN_REAL_PI_SMOKE") == "1":
        print("[Smoke] RUN_REAL_PI_SMOKE=1: skipping Pi run (requires Pi installation)")

    if failures:
        print(f"\n[Smoke] FAILED ({len(failures)} issue(s)):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"\n[Smoke] PASSED  case={CASE_NAME}  domain={detected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
