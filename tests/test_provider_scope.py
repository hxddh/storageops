from __future__ import annotations

import importlib.util
from pathlib import Path


def load_gate():
    root = Path(__file__).resolve().parents[1]
    p = root / "scripts" / "provider_scope_check.py"
    spec = importlib.util.spec_from_file_location("provider_scope_check", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_repo_passes_provider_scope():
    gate = load_gate()
    assert gate.main() == 0


def test_unscoped_aws_locked_helper_fails(tmp_path, monkeypatch):
    gate = load_gate()
    bad = tmp_path / "bad.py"
    # AWS-locked (amazonaws.com), no --provider, no scope marker -> must fail.
    bad.write_text('PRINCIPAL = "s3.amazonaws.com"\n', encoding="utf-8")
    monkeypatch.setattr(gate, "SCRIPTS", [bad])
    assert gate.main() == 1


def test_scoped_aws_locked_helper_passes(tmp_path, monkeypatch):
    gate = load_gate()
    ok = tmp_path / "ok.py"
    ok.write_text('"""AWS-specific helper."""\nP = "s3.amazonaws.com"\n', encoding="utf-8")
    monkeypatch.setattr(gate, "SCRIPTS", [ok])
    assert gate.main() == 0


def test_provider_parameterised_helper_is_exempt(tmp_path, monkeypatch):
    gate = load_gate()
    multi = tmp_path / "multi.py"
    # AWS token present but provider-parameterised -> exempt, no marker required.
    multi.write_text('ap.add_argument("--provider")\nP = "arn:aws:iam::1:root"\n', encoding="utf-8")
    monkeypatch.setattr(gate, "SCRIPTS", [multi])
    assert gate.main() == 0
