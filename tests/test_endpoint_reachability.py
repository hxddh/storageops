from __future__ import annotations

import importlib.util
from pathlib import Path


def load_checker_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-network-endpoint-access" / "scripts" / "endpoint_reachability_test.py"
    spec = importlib.util.spec_from_file_location("endpoint_reachability_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_endpoint_defaults_to_https():
    checker = load_checker_module()
    endpoint = checker.parse_endpoint("s3.example.com/bucket")

    assert endpoint.scheme == "https"
    assert endpoint.host == "s3.example.com"
    assert endpoint.port == 443
    assert endpoint.path == "/bucket"


def test_classify_dns_failure():
    checker = load_checker_module()
    result = {
        "checks": {
            "dns": {"ok": False},
            "tcp": {"ok": False},
            "tls": {"ok": False},
            "http_head": {"ok": False},
        }
    }

    assert checker.classify_failure(result) == "DNS"


def test_run_checks_marks_application_status_as_network_reachable(monkeypatch):
    checker = load_checker_module()
    endpoint = checker.parse_endpoint("https://s3.example.com")

    monkeypatch.setattr(checker, "check_dns", lambda endpoint: {"ok": True, "addresses": ["192.0.2.10"]})
    monkeypatch.setattr(checker, "check_tcp", lambda endpoint, timeout: {"ok": True})
    monkeypatch.setattr(checker, "check_tls", lambda endpoint, timeout, verify: {"ok": True, "tls_version": "TLSv1.3"})
    monkeypatch.setattr(checker, "check_http_head", lambda endpoint, timeout, verify: {"ok": True, "status": 403, "reason": "Forbidden"})

    result = checker.run_checks(endpoint, timeout=1.0, verify_tls=True)

    assert result["classification"] == "application"
    assert result["ok"] is True
