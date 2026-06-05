from __future__ import annotations

import importlib.util
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "skills" / "storageops-mount-filesystem-workspace" / "scripts" / "mount_workload_analyzer.py"
    spec = importlib.util.spec_from_file_location("mount_workload_analyzer", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_git_is_unsuitable_with_posix_gaps():
    m = load()
    r = m.analyze("s3fs", "git", files=5000, rtt_ms=30)
    assert r["suitable"] is False
    assert any("atomic rename" in u for u in r["unsupported_posix"])
    assert any("locking" in u for u in r["unsupported_posix"])
    assert r["metadata_amplification"] == "very-high"
    # worst-case serialized estimate is surfaced when files+rtt provided
    assert r["estimated_head_ops"] == 15000
    assert r["estimated_serialized_seconds_worst_case"] == 450.0
    assert "local disk" in r["recommendation"]


def test_read_only_dataset_is_suitable():
    m = load()
    r = m.analyze("s3fs", "read-only", files=100000, rtt_ms=20)
    assert r["suitable"] is True
    assert r["unsupported_posix"] == []
    assert "caching" in r["recommendation"]


def test_database_flags_locking_and_mmap():
    m = load()
    r = m.analyze("goofys", "database", files=None, rtt_ms=None)
    assert r["suitable"] is False
    assert any("locking" in u for u in r["unsupported_posix"])
    assert any("mmap" in u for u in r["unsupported_posix"])
    # goofys has no local metadata cache in our table
    assert r["stale_cache_risk"].startswith("n/a")


def test_caching_tool_flags_stale_risk():
    m = load()
    r = m.analyze("s3fs", "ls-find", files=10, rtt_ms=None)
    assert r["stale_cache_risk"].startswith("elevated")
