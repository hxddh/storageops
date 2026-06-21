from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-evidence-reporting" / "scripts" / "report_contract_validator.py"
    spec = importlib.util.spec_from_file_location("rcv", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


GOOD = "## Summary\nresult (confidence: 0.82)\n## Key Evidence\n- a\n## Remediation\n- add a bucket policy allow\n"


def test_good_report_passes():
    m = load()
    r = m.validate(GOOD, m.DEFAULT_SECTIONS)
    assert r["ok"] is True and r["missing_sections"] == []


def test_missing_section():
    m = load()
    r = m.validate("## Summary\nx (confidence: high)\n## Key Evidence\n- a\n", m.DEFAULT_SECTIONS)
    assert r["ok"] is False and "Remediation" in r["missing_sections"]


def test_unsafe_recommendation_flagged():
    m = load()
    r = m.validate("## Summary\nx (confidence: 0.5)\n## Key Evidence\n- a\n## Remediation\n- just make the bucket public\n", m.DEFAULT_SECTIONS)
    assert r["ok"] is False and r["unsafe_findings"]


def test_secret_flagged():
    m = load()
    r = m.validate("## Summary\nx (confidence: 0.5)\n## Key Evidence\n- key AKIAIOSFODNN7EXAMPLE\n## Remediation\n- rotate\n", m.DEFAULT_SECTIONS)
    assert r["ok"] is False and "AWS access key id" in r["secret_findings"]


def test_missing_confidence():
    m = load()
    r = m.validate("## Summary\nx\n## Key Evidence\n- a\n## Remediation\n- b\n", m.DEFAULT_SECTIONS)
    assert r["ok"] is False and r["confidence_present"] is False


def test_qualitative_confidence_ok():
    m = load()
    r = m.validate("## Summary\nx confidence: medium\n## Key Evidence\n- a\n## Remediation\n- b\n", m.DEFAULT_SECTIONS)
    assert r["ok"] is True
