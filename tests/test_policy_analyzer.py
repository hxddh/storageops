import importlib.util
import json
import subprocess
import sys
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


def test_missing_file_emits_json_error_not_traceback(tmp_path):
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-security-iam-policy" / "scripts" / "policy_analyzer.py"
    missing = tmp_path / "does_not_exist.json"

    proc = subprocess.run(
        [sys.executable, str(module_path), "--file", str(missing)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert str(missing) in payload["error"]
    assert "Traceback" not in proc.stderr
