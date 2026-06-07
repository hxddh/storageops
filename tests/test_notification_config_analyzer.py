from __future__ import annotations

import importlib.util
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-event-notification" / "scripts" / "notification_config_analyzer.py"
    spec = importlib.util.spec_from_file_location("notification_config_analyzer", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _cfg(events, prefix="", suffix=""):
    rule = {"Id": "r1", "LambdaFunctionArn": "arn:aws:lambda:::fn", "Events": events}
    fr = []
    if prefix:
        fr.append({"Name": "prefix", "Value": prefix})
    if suffix:
        fr.append({"Name": "suffix", "Value": suffix})
    if fr:
        rule["Filter"] = {"Key": {"FilterRules": fr}}
    return {"LambdaFunctionConfigurations": [rule]}


def test_no_config():
    m = load()
    assert m.analyze({}, None, "")["verdict"] == "no_notification_config"


def test_event_type_mismatch_multipart():
    m = load()
    r = m.analyze(_cfg(["s3:ObjectCreated:Put"]), "a.bin", "s3:ObjectCreated:CompleteMultipartUpload")
    assert r["verdict"] == "event_type_mismatch"
    assert "multipart" in r["likely_cause"].lower()


def test_wildcard_event_matches():
    m = load()
    r = m.analyze(_cfg(["s3:ObjectCreated:*"]), "a.jpg", "s3:ObjectCreated:CompleteMultipartUpload")
    assert r["verdict"] == "would_fire"


def test_filter_mismatch_suffix():
    m = load()
    r = m.analyze(_cfg(["s3:ObjectCreated:*"], suffix=".png"), "uploads/a.jpg", "s3:ObjectCreated:Put")
    assert r["verdict"] == "filter_mismatch"
    assert "suffix" in r["likely_cause"]


def test_would_fire_points_at_target_policy():
    m = load()
    r = m.analyze(_cfg(["s3:ObjectCreated:Put"], prefix="uploads/"), "uploads/a.jpg", "s3:ObjectCreated:Put")
    assert r["verdict"] == "would_fire"
    assert "lambda:InvokeFunction" in r["recommendation"]
    assert r["matching_rules"][0]["target_type"] == "lambda"
