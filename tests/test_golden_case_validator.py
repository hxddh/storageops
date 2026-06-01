import importlib.util
import json
from pathlib import Path


def load_validator():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-eval-golden-cases" / "scripts" / "golden_case_validator.py"
    spec = importlib.util.spec_from_file_location("golden_case_validator", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write_minimal_case(case: Path, secret_text: str):
    (case / "input").mkdir(parents=True)
    (case / "expected.json").write_text(
        json.dumps(
            {
                "expected_category": "security_iam_policy",
                "expected_min_confidence": 0.8,
                "must_include_evidence_keywords": ["AccessDenied"],
                "must_include_recommendation_keywords": ["policy"],
                "must_not_include": ["delete bucket"],
                "required_report_sections": ["Summary"],
            }
        )
    )
    (case / "input" / "evidence.txt").write_text(secret_text)


def test_example_marker_only_whitelists_the_secret_token(tmp_path):
    validator = load_validator()
    case = tmp_path / "case"
    write_minimal_case(case, "EXAMPLE prose nearby\nreal key AKIAABCDEFGHIJKLMNOP\n")

    errors = validator.validate_case(case, {"security_iam_policy": "storageops-security-iam-policy"})

    assert any("possible unredacted secret" in error for error in errors)


def test_example_marker_inside_token_is_allowed(tmp_path):
    validator = load_validator()
    case = tmp_path / "case"
    write_minimal_case(case, "sample key AKIAEXAMPLE123456789\n")

    errors = validator.validate_case(case, {"security_iam_policy": "storageops-security-iam-policy"})

    assert not errors
