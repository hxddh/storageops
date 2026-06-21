from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-triage" / "scripts" / "evidence_completeness_checker.py"
    spec = importlib.util.spec_from_file_location("ecc", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_ready_when_most_evidence_present():
    m = load()
    r = m.check("security", "403 AccessDenied request id abc on s3:GetObject for arn:aws:iam::1:user/a; "
                            "bucket policy with principal/resource; using an assumed role; condition StringEquals")
    assert r["ok"] is True
    assert r["verdict"] == "ready" and r["readiness"] >= 0.8


def test_insufficient_when_sparse():
    m = load()
    r = m.check("performance", "it is slow")
    assert r["verdict"] in ("insufficient", "partial")
    assert "missing" in r and len(r["missing"]) > 0


def test_aliases_resolve():
    m = load()
    assert m._resolve_domain("iam") == "security_iam_policy"
    assert m._resolve_domain("storageops-network-endpoint-access") is None or m._resolve_domain("network") == "network_endpoint_access"
    assert m._resolve_domain("cost") == "lifecycle_cost"


def test_unknown_domain_ok_false():
    m = load()
    assert m.check("banana", "x")["ok"] is False


def test_cli_stdin(capsys, monkeypatch):
    m = load()
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("endpoint dns dig vpc tls ping proxy"))
    rc = m.main(["--domain", "network", "--stdin"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["domain"] == "network_endpoint_access"
