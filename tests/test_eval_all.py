from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_eval_all_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-eval-golden-cases" / "scripts" / "eval_all.py"
    spec = importlib.util.spec_from_file_location("eval_all", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_case(cases_root: Path, name: str, category: str, evidence: str, recommendation: str) -> Path:
    case = cases_root / name
    case.mkdir()
    (case / "expected.json").write_text(
        json.dumps(
            {
                "expected_category": category,
                "expected_min_confidence": 0.7,
                "must_include_evidence_keywords": [evidence],
                "must_include_recommendation_keywords": [recommendation],
                "must_not_include": ["delete bucket"],
                "required_report_sections": ["Routing"],
            }
        ),
        encoding="utf-8",
    )
    return case


def test_evaluate_all_summarizes_outputs_and_missing_cases(tmp_path):
    eval_all = load_eval_all_module()
    cases = tmp_path / "cases"
    outputs = tmp_path / "outputs"
    cases.mkdir()
    outputs.mkdir()
    write_case(cases, "sigv4", "s3_protocol_compatibility", "SignatureDoesNotMatch", "endpoint")
    write_case(cases, "missing", "security_iam_policy", "AccessDenied", "policy")
    (outputs / "sigv4.md").write_text(
        """
# Routing
Route to storageops-s3-protocol-compatibility.
Confidence: 0.8
Evidence: SignatureDoesNotMatch from endpoint.
Recommendation: inspect endpoint region.
""",
        encoding="utf-8",
    )

    report = eval_all.evaluate_all(cases, outputs, ".md")

    assert report["summary"]["total"] == 2
    assert report["summary"]["counts"]["PASS"] == 1
    assert report["summary"]["counts"]["MISSING"] == 1
    assert report["summary"]["by_category"]["s3_protocol_compatibility"]["PASS"] == 1
    assert report["summary"]["by_category"]["security_iam_policy"]["MISSING"] == 1


def test_evaluate_all_can_score_only_cases_with_outputs(tmp_path):
    eval_all = load_eval_all_module()
    cases = tmp_path / "cases"
    outputs = tmp_path / "outputs"
    cases.mkdir()
    outputs.mkdir()
    write_case(cases, "sigv4", "s3_protocol_compatibility", "SignatureDoesNotMatch", "endpoint")
    write_case(cases, "missing", "security_iam_policy", "AccessDenied", "policy")
    (outputs / "sigv4.md").write_text(
        """
# Routing
Route to storageops-s3-protocol-compatibility.
Confidence: 0.8
Evidence: SignatureDoesNotMatch from endpoint.
Recommendation: inspect endpoint region.
""",
        encoding="utf-8",
    )

    report = eval_all.evaluate_all(cases, outputs, ".md", only_with_outputs=True)

    assert report["summary"]["total"] == 1
    assert report["summary"]["counts"]["PASS"] == 1
    assert report["summary"]["counts"]["MISSING"] == 0
