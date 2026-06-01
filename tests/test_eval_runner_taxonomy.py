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


def write_case(tmp_path: Path, expected_category: str) -> Path:
    case = tmp_path / "case"
    case.mkdir()
    (case / "expected.json").write_text(
        json.dumps(
            {
                "expected_category": expected_category,
                "expected_min_confidence": 0.7,
                "must_include_evidence_keywords": ["SignatureDoesNotMatch"],
                "must_include_recommendation_keywords": ["endpoint"],
                "must_not_include": ["delete bucket"],
                "required_report_sections": ["Routing"],
            }
        ),
        encoding="utf-8",
    )
    return case


def test_eval_accepts_mapped_skill_name_for_category(tmp_path):
    runner = load_eval_runner_module()
    case = write_case(tmp_path, "s3_protocol_compatibility")
    output = tmp_path / "diagnosis.md"
    output.write_text(
        """
# Routing
Route to storageops-s3-protocol-compatibility.
Evidence: SignatureDoesNotMatch from an S3-compatible endpoint.
Recommendation: compare endpoint region and canonical request details.
""",
        encoding="utf-8",
    )

    result = runner.evaluate(case, output)

    assert result["status"] == "PASS"


def test_eval_fails_when_neither_category_nor_skill_is_present(tmp_path):
    runner = load_eval_runner_module()
    case = write_case(tmp_path, "s3_protocol_compatibility")
    output = tmp_path / "diagnosis.md"
    output.write_text(
        """
# Routing
Evidence: SignatureDoesNotMatch in the response.
Recommendation: inspect endpoint settings.
""",
        encoding="utf-8",
    )

    result = runner.evaluate(case, output)

    assert result["status"] == "HARD_FAIL"
    assert "expected_category or mapped skill not found" in result["failures"][0]
