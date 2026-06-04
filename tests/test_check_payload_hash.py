from __future__ import annotations

import gzip
import hashlib
import importlib.util
from pathlib import Path


def load_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-s3-protocol-compatibility" / "scripts" / "check_payload_hash.py"
    spec = importlib.util.spec_from_file_location("check_payload_hash", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hash_over_pre_encoding_is_flagged():
    m = load_module()
    raw = b"hello world\n" * 100
    declared = hashlib.sha256(raw).hexdigest()
    result = m.analyze(raw, declared, "gzip", None)
    assert result["declared_matches"] == "raw"
    assert result["verdict"] == "payload_hash_over_pre_encoding"
    assert "compressed body" in result["fix"]
    # implementation-dependent gzip note is surfaced when sent body is absent
    assert any("implementation-dependent" in n for n in result["notes"])


def test_declared_matches_sent_body_is_ok():
    m = load_module()
    raw = b"payload-bytes"
    sent = gzip.compress(raw)
    declared = hashlib.sha256(sent).hexdigest()
    result = m.analyze(raw, declared, "gzip", sent)
    assert result["declared_matches"] == "sent"
    assert result["verdict"] == "ok"


def test_unknown_when_declared_matches_neither():
    m = load_module()
    raw = b"the-object"
    declared = hashlib.sha256(b"something-else").hexdigest()
    result = m.analyze(raw, declared, None, None)
    assert result["declared_matches"] == "none"
    assert result["verdict"] == "unknown"


def test_raw_match_without_transform_is_inconclusive():
    m = load_module()
    raw = b"no-transform-here"
    declared = hashlib.sha256(raw).hexdigest()
    result = m.analyze(raw, declared, None, None)
    assert result["declared_matches"] == "raw"
    assert result["verdict"] == "declared_matches_raw_no_transform_evidence"


def test_cli_rejects_bad_declared_hex(capsys):
    m = load_module()
    rc = m.main(["--raw-file", __file__, "--declared-sha256", "not-a-hash"])
    assert rc == 2
