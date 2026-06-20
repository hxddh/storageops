#!/usr/bin/env python3
"""Tests for lifecycle_rule_simulator: structural cost risks, no currency."""

import importlib.util
import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
_module_path = _root / "skills" / "storageops-lifecycle-cost" / "scripts" / "lifecycle_rule_simulator.py"
_spec = importlib.util.spec_from_file_location("lifecycle_rule_simulator", _module_path)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
run, analyze, _parse_config = _mod.run, _mod.analyze, _mod._parse_config  # noqa: E402


def _no_currency(result: dict) -> None:
    blob = json.dumps(result, ensure_ascii=False)
    for sym in ("$", "¥", "USD", "CNY", "RMB"):
        assert sym not in blob, f"currency token {sym!r} leaked into output"


def _stdin(monkeypatch, text):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_ia_min_duration_early_deletion(monkeypatch):
    # STANDARD_IA (30-day min) entered at day 10, expired at day 20 -> wasted.
    cfg = json.dumps({"Rules": [{
        "ID": "r", "Status": "Enabled",
        "Transitions": [{"Days": 10, "StorageClass": "STANDARD_IA"}],
        "Expiration": {"Days": 20},
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
    }]})
    _stdin(monkeypatch, cfg)
    result = run(use_stdin=True, age_days=25)
    assert result["ok"] is True
    risks = result["min_duration_risks"]
    assert any(r["class"] == "STANDARD_IA" and r["min_days"] == 30 and r["wasted_days"] == 20
               for r in risks)
    _no_currency(result)


def test_glacier_premature_archive():
    # 30 -> GLACIER then expire at 60; GLACIER min duration is 90 -> 60 wasted.
    cfg = json.dumps({"Rules": [{
        "ID": "archive", "Status": "Enabled",
        "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}],
        "Expiration": {"Days": 60},
    }]})
    parsed = _parse_config(cfg)
    result = analyze(parsed["rules"], age_days=70, avg_size=None,
                     object_count=None, start_class="STANDARD")
    risk = next(r for r in result["min_duration_risks"] if r["class"] == "GLACIER")
    assert risk["min_days"] == 90
    assert risk["wasted_days"] == 60
    assert "90" in result["summary"]
    _no_currency(result)


def test_small_object_size_multiplier(monkeypatch):
    cfg = """<LifecycleConfiguration><Rule><ID>r</ID><Status>Enabled</Status>
      <Transition><Days>30</Days><StorageClass>STANDARD_IA</StorageClass></Transition>
      <AbortIncompleteMultipartUpload><DaysAfterInitiation>7</DaysAfterInitiation></AbortIncompleteMultipartUpload>
      </Rule></LifecycleConfiguration>"""
    _stdin(monkeypatch, cfg)
    result = run(use_stdin=True, age_days=40, avg_size=1024, object_count=1000)
    sp = result["size_penalty"]
    assert sp is not None
    assert sp["min_billable_bytes"] == 131072  # 128 KB, reused from analyzer
    assert sp["multiplier"] == 128.0
    assert sp["object_count"] == 1000
    _no_currency(result)


def test_no_size_penalty_for_large_objects():
    cfg = json.dumps({"Rules": [{
        "ID": "r", "Status": "Enabled",
        "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}],
        "AbortIncompleteMultipartUpload": {"x": 1},
    }]})
    parsed = _parse_config(cfg)
    result = analyze(parsed["rules"], age_days=40, avg_size=1048576,
                     object_count=10, start_class="STANDARD")
    assert result["size_penalty"] is None
    _no_currency(result)


def test_missing_abort_multipart():
    cfg = json.dumps({"Rules": [{
        "ID": "noabort", "Status": "Enabled",
        "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}],
    }]})
    parsed = _parse_config(cfg)
    result = analyze(parsed["rules"], age_days=40, avg_size=None,
                     object_count=None, start_class="STANDARD")
    assert any("AbortIncompleteMultipartUpload" in w for w in result["warnings"])
    assert "AbortIncompleteMultipartUpload" in result["recommendation"]
    _no_currency(result)


def test_rule_conflict_transition_after_expiration():
    cfg = json.dumps({"Rules": [{
        "ID": "conflict", "Status": "Enabled",
        "Transitions": [{"Days": 100, "StorageClass": "GLACIER"}],
        "Expiration": {"Days": 60},
        "AbortIncompleteMultipartUpload": {"x": 1},
    }]})
    parsed = _parse_config(cfg)
    result = analyze(parsed["rules"], age_days=200, avg_size=None,
                     object_count=None, start_class="STANDARD")
    assert any("never fires" in w for w in result["warnings"])
    _no_currency(result)


def test_empty_input(monkeypatch):
    _stdin(monkeypatch, "")
    result = run(use_stdin=True)
    assert result["ok"] is False
    _no_currency(result)


def test_malformed_json(monkeypatch):
    _stdin(monkeypatch, "{not valid json")
    result = run(use_stdin=True)
    assert result["ok"] is False
    assert "error" in result
    _no_currency(result)


def test_malformed_xml(monkeypatch):
    _stdin(monkeypatch, "<Lifecycle><Rule>unclosed")
    result = run(use_stdin=True)
    assert result["ok"] is False
    _no_currency(result)


def test_disabled_rule_warns():
    cfg = json.dumps({"Rules": [{
        "ID": "off", "Status": "Disabled",
        "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}],
    }]})
    parsed = _parse_config(cfg)
    result = analyze(parsed["rules"], age_days=40, avg_size=None,
                     object_count=None, start_class="STANDARD")
    assert any("Disabled" in w for w in result["warnings"])
    # Disabled rule contributes no min-duration risk.
    assert result["min_duration_risks"] == []
    _no_currency(result)


def test_no_dollar_sign_in_serialized_output():
    cfg = json.dumps({"Rules": [{
        "ID": "r", "Status": "Enabled",
        "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}],
        "Expiration": {"Days": 60},
    }]})
    parsed = _parse_config(cfg)
    result = analyze(parsed["rules"], age_days=70, avg_size=1024,
                     object_count=5, start_class="STANDARD")
    assert "$" not in json.dumps(result, ensure_ascii=False)
