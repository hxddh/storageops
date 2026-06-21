from __future__ import annotations

import importlib.util
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "scripts" / "contract_check.py"
    spec = importlib.util.spec_from_file_location("contract_check", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_repo_passes_contract():
    assert load().main() == 0


def test_headings_extraction():
    m = load()
    h = m._headings("# A\n## Summary\ntext\n### Key Evidence\n")
    assert "Summary" in h and "Key Evidence" in h


def test_required_sets_are_canonical():
    m = load()
    assert "Key Evidence" in m.DIAGNOSTIC_REQUIRED and "Remediation" in m.DIAGNOSTIC_REQUIRED
    assert m.SPECIAL["storageops-triage"] == ["Routing", "Evidence Gaps"]
