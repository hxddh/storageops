from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-event-notification" / "scripts" / "notification_target_policy_validator.py"
    spec = importlib.util.spec_from_file_location("notification_target_policy_validator", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BUCKET = "arn:aws:s3:::source-bucket"


def _lambda_policy(action="lambda:InvokeFunction", principal_service="s3.amazonaws.com", source_arn=BUCKET):
    stmt = {
        "Sid": "AllowS3Invoke",
        "Effect": "Allow",
        "Principal": {"Service": principal_service},
        "Action": action,
        "Resource": "arn:aws:lambda:us-east-1:111122223333:function:fn",
    }
    if source_arn:
        stmt["Condition"] = {"ArnLike": {"aws:SourceArn": source_arn}}
    # Lambda get-policy wraps the document as a JSON string under "Policy".
    return json.dumps({"Policy": json.dumps({"Version": "2012-10-17", "Statement": [stmt]})})


def test_valid_lambda_policy():
    m = load()
    r = m.validate(m._load_policy(_lambda_policy()), "lambda", BUCKET)
    assert r["ok"] is True
    assert r["target_type"] == "lambda"
    assert r["policy_ok"] is True
    assert r["missing"] == []


def test_missing_invoke_function():
    m = load()
    # Principal correct, but action is GetFunction, not InvokeFunction.
    r = m.validate(m._load_policy(_lambda_policy(action="lambda:GetFunction")), "lambda", BUCKET)
    assert r["policy_ok"] is False
    assert any("lambda:InvokeFunction" in item for item in r["missing"])


def test_wrong_principal():
    m = load()
    r = m.validate(m._load_policy(_lambda_policy(principal_service="events.amazonaws.com")), "lambda", BUCKET)
    assert r["policy_ok"] is False
    assert any("s3.amazonaws.com" in item for item in r["missing"])


def test_sqs_valid():
    m = load()
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "s3.amazonaws.com"},
            "Action": "sqs:SendMessage",
            "Resource": "arn:aws:sqs:us-east-1:111122223333:events",
            "Condition": {"ArnLike": {"aws:SourceArn": BUCKET}},
        }],
    }
    # Auto-detect target type from the sqs:SendMessage action.
    r = m.validate(policy, None, BUCKET)
    assert r["target_type"] == "sqs"
    assert r["policy_ok"] is True


def test_sourcearn_mismatch():
    m = load()
    r = m.validate(m._load_policy(_lambda_policy(source_arn="arn:aws:s3:::other-bucket")), "lambda", BUCKET)
    assert r["policy_ok"] is False
    assert any("SourceArn" in item for item in r["missing"])


def test_empty_input_emits_ok_false(capsys):
    m = load()
    rc = m.main(["--stdin"])  # no stdin content in pytest -> empty string
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["policy_ok"] is False


def test_malformed_input(tmp_path, capsys):
    m = load()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = m.main(["--file", str(bad)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert "valid_policy_json" in out["missing"]
