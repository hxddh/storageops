from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-replication-versioning" / "scripts" / "replication_status_analyzer.py"
    spec = importlib.util.spec_from_file_location("replication_status_analyzer", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_destination_versioning_disabled():
    m = load()
    text = (
        "Destination bucket versioning:\n"
        "  $ aws s3api get-bucket-versioning --bucket prod-backup\n"
        "  {}\n"
        'head-object: {"ReplicationStatus": "FAILED"}\n'
    )
    r = m.analyze(text)
    assert r["ok"] is False
    assert r["root_cause"] == "dest_versioning_disabled"
    assert "enable versioning" in r["recommendation"].lower()


def test_golden_crr_case():
    m = load()
    root = Path(__file__).resolve().parents[1]
    inp = root / "skills" / "storageops-eval-golden-cases" / "cases" / "crr-replication-lag" / "input" / "replication-error.txt"
    r = m.analyze(inp.read_text(encoding="utf-8"))
    assert r["root_cause"] == "dest_versioning_disabled"
    assert any("847" in f for f in r["findings"])


def test_disabled_rule():
    m = load()
    cfg = json.dumps({
        "ReplicationConfiguration": {
            "Role": "arn:aws:iam::1:role/r",
            "Rules": [{"ID": "r1", "Status": "Disabled", "Destination": {"Bucket": "arn:aws:s3:::dest"}}],
        }
    })
    r = m.analyze(cfg)
    assert r["ok"] is False
    assert r["root_cause"] == "rule_disabled"


def test_delete_marker_not_replicated():
    m = load()
    cfg = json.dumps({
        "ReplicationConfiguration": {
            "Rules": [{
                "ID": "r1",
                "Status": "Enabled",
                "Destination": {"Bucket": "arn:aws:s3:::dest"},
                "DeleteMarkerReplication": {"Status": "Disabled"},
            }]
        }
    })
    r = m.analyze(cfg)
    assert r["ok"] is False
    assert r["root_cause"] == "delete_marker_not_replicated"
    assert "DeleteMarkerReplication" in r["recommendation"]


def test_source_versioning_suspended():
    m = load()
    text = '$ aws s3api get-bucket-versioning --bucket source\n{"Status": "Suspended"}\n'
    r = m.analyze(text)
    assert r["root_cause"] == "source_versioning_suspended"


def test_empty_input():
    m = load()
    r = m.analyze("")
    assert r["ok"] is False
    assert r["root_cause"] == "no_input"


def test_malformed_input_no_traceback():
    m = load()
    r = m.analyze("{not valid json :::: <garbage> }")
    assert isinstance(r, dict)
    assert r["ok"] in (True, False)
    assert "root_cause" in r


def test_healthy_config():
    m = load()
    cfg = json.dumps({
        "ReplicationConfiguration": {
            "Rules": [{
                "ID": "r1",
                "Status": "Enabled",
                "Destination": {"Bucket": "arn:aws:s3:::dest"},
                "DeleteMarkerReplication": {"Status": "Enabled"},
            }]
        }
    })
    r = m.analyze(cfg)
    assert r["ok"] is True
    assert r["root_cause"] == "healthy"
