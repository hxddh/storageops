"""
LLM smoke test: run one golden case through the full agent loop and
validate the report structure. Used in the llm-smoke-test CI workflow.

Exit code 0 = pass, 1 = fail.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_CORE = _ROOT / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

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

    from storageops.llm_agent import run_llm_agent
    from storageops.report_validator import validate_report

    expected_category = expected["expected_category"]
    print(f"[Smoke] Case: {CASE_NAME}  expected_category: {expected_category}")

    result = run_llm_agent(
        evidence_text=evidence_text,
        domain=expected_category,
        provider_name="anthropic",
        max_turns=6,
        verbose=True,
    )

    failures: list[str] = []

    if not result["ok"]:
        failures.append(f"agent returned ok=False: {result.get('error')}")

    # Validate YAML frontmatter
    validation = validate_report(result.get("report", ""))
    if not validation["valid"]:
        failures.append(
            f"report validation failed: missing={validation['missing_fields']} "
            f"invalid={validation['invalid_fields']}"
        )

    # Check root_cause_type is in expected set
    expected_rcts = set(expected.get("expected_root_cause_types", []))
    actual_rct = result.get("root_cause", "unknown")
    if expected_rcts and actual_rct not in expected_rcts and actual_rct != "unknown":
        print(
            f"[Smoke] WARN: root_cause_type={actual_rct!r} not in expected {expected_rcts} "
            "(non-fatal — root cause naming can vary)"
        )

    # Check must_not_include
    report_lower = result.get("report", "").lower()
    for forbidden in expected.get("must_not_include", []):
        if forbidden.lower() in report_lower:
            failures.append(f"report contains forbidden phrase: {forbidden!r}")

    if failures:
        print(f"\n[Smoke] FAILED ({len(failures)} issue(s)):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"\n[Smoke] PASSED  session={result['session_id']}  "
        f"turns={result['turns_used']}  root_cause={actual_rct}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
