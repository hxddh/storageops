import importlib.util
from pathlib import Path


def load_policy_analyzer():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-security-iam-policy" / "scripts" / "policy_analyzer.py"
    spec = importlib.util.spec_from_file_location("policy_analyzer", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_public_aws_principal_list_is_flagged():
    analyzer = load_policy_analyzer()
    result = analyzer.analyze(
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": "s3:GetObject",
                    "Resource": "arn:aws:s3:::bucket/*",
                }
            ]
        }
    )

    assert result["ok"] is False
    assert "public_access_risk" in result["details"]


def test_allow_not_action_and_broad_resource_are_flagged():
    analyzer = load_policy_analyzer()
    result = analyzer.analyze(
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "*"},
                    "NotAction": "s3:DeleteBucket",
                    "Resource": "*",
                }
            ]
        }
    )

    assert result["ok"] is False
    assert "public_access_risk" in result["details"]
    assert "not_action_risk" in result["details"]
    assert "broad_resource_risk" in result["details"]


def test_explicit_deny_is_informational_not_an_issue():
    analyzer = load_policy_analyzer()
    result = analyzer.analyze(
        {
            "Statement": [
                {
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": "*",
                }
            ]
        }
    )

    assert result["ok"] is True
    assert "explicit_denies" in result["details"]
