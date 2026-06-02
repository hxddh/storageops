from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_eval_runner_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-eval-golden-cases" / "scripts" / "eval_runner.py"
    spec = importlib.util.spec_from_file_location("eval_runner", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_case(tmp_path: Path, *, category: str = "s3_protocol_compatibility") -> Path:
    case = tmp_path / "case"
    case.mkdir()
    (case / "expected.json").write_text(
        json.dumps(
            {
                "expected_category": category,
                "expected_min_confidence": 0.7,
                "must_include_evidence_keywords": ["s3:GetObject", "GET"],
                "must_include_recommendation_keywords": ["endpoint"],
                "must_not_include": ["delete bucket"],
                "required_report_sections": ["Routing"],
            }
        ),
        encoding="utf-8",
    )
    return case


def test_keyword_matcher_handles_symbols_and_short_tokens():
    runner = load_eval_runner_module()

    assert runner.keyword_present("Action is s3:GetObject on the object", "s3:GetObject")
    assert runner.keyword_present("HTTP GET returned 403", "GET")
    assert not runner.keyword_present("Do not forget endpoint validation", "GET")


def test_forbidden_matcher_ignores_safe_negation():
    runner = load_eval_runner_module()

    assert runner.forbidden_hits("Do not delete bucket during remediation.", ["delete bucket"]) == []
    assert runner.forbidden_hits("Recommended action: delete bucket now.", ["delete bucket"])


def test_category_field_takes_precedence_over_misleading_body(tmp_path):
    runner = load_eval_runner_module()
    case = write_case(tmp_path)
    output = tmp_path / "diagnosis.md"
    output.write_text(
        """
# Routing
Category: security_iam_policy
Route: storageops-security-iam-policy
Confidence: 0.9
Evidence: s3:GetObject failed on HTTP GET.
Recommendation: inspect endpoint configuration.
Body mentions storageops-s3-protocol-compatibility only as a rejected route.
""",
        encoding="utf-8",
    )

    result = runner.evaluate(case, output)

    assert result["status"] == "HARD_FAIL"
    assert "expected_category or mapped skill not found" in result["failures"][0]


def test_confidence_accepts_percent_format(tmp_path):
    runner = load_eval_runner_module()
    case = write_case(tmp_path)
    output = tmp_path / "diagnosis.md"
    output.write_text(
        """
# Routing
Route: storageops-s3-protocol-compatibility
Confidence: 82%
Evidence: s3:GetObject failed on HTTP GET.
Recommendation: inspect endpoint configuration.
""",
        encoding="utf-8",
    )

    result = runner.evaluate(case, output)

    assert result["status"] == "PASS"
