from __future__ import annotations

import importlib.util
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-access-log-analysis" / "scripts" / "parse_access_log.py"
    spec = importlib.util.spec_from_file_location("parse_access_log", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _records():
    return [
        {"status": 503, "error_code": "SlowDown", "requester": "a", "operation": "GET", "bytes_sent": 0, "key": "hot/2026/f1"},
        {"status": 503, "error_code": "SlowDown", "requester": "a", "operation": "GET", "bytes_sent": 0, "key": "hot/2026/f2"},
        {"status": 200, "error_code": None, "requester": "a", "operation": "GET", "bytes_sent": 1, "key": "hot/2026/f3"},
        {"status": 200, "error_code": None, "requester": "a", "operation": "GET", "bytes_sent": 1, "key": "cold/f4"},
    ]


def test_prefix_of_truncates_to_depth():
    m = load()
    assert m._prefix_of("a/b/c/d", 2) == "a/b/"
    assert m._prefix_of("a/b", 2) == "a/b"
    assert m._prefix_of("/leading/slash/x", 1) == "leading/"
    assert m._prefix_of("-", 1) == "<root>"


def test_breakdown_localizes_hot_prefix():
    m = load()
    bd = m._prefix_breakdown(_records(), depth=1)
    by = {b["prefix"]: b for b in bd}
    assert by["hot/"]["count"] == 3
    assert by["hot/"]["throttles"] == 2
    assert by["hot/"]["errors"] == 2
    assert by["cold/"]["throttles"] == 0


def test_aggregate_emits_prefix_finding():
    m = load()
    out = m._aggregate(_records(), "s3", 0, prefix_depth=1)
    assert "prefix_breakdown" in out["details"]
    assert out["details"]["prefix_depth"] == 1
    assert any("hot/" in f and "hot prefix" in f for f in out["findings"])


def test_no_prefix_depth_keeps_output_unchanged():
    m = load()
    out = m._aggregate(_records(), "s3", 0)
    assert "prefix_breakdown" not in out["details"]


def test_end_to_end_by_prefix_flag():
    m = load()
    lines = [
        'own bkt [06/Jun/2026:00:00:01 +0000] 1.2.3.4 arn:user/a r1 REST.GET.OBJECT hot/2026/f1 "GET /hot/2026/f1" 503 SlowDown 0 100 5 5 "-" "cli" -',
        'own bkt [06/Jun/2026:00:00:02 +0000] 1.2.3.4 arn:user/a r2 REST.GET.OBJECT cold/f2 "GET /cold/f2" 200 - 100 100 5 5 "-" "cli" -',
    ]
    out = m.parse_s3_log(lines, prefix_depth=1)
    prefixes = {b["prefix"] for b in out["details"]["prefix_breakdown"]}
    assert prefixes == {"hot/", "cold/"}
