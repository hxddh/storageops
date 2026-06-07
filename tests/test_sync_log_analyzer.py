from __future__ import annotations

import importlib.util
from pathlib import Path


def load():
    root = Path(__file__).resolve().parents[1]
    p = root / "skills" / "storageops-migration-sync" / "scripts" / "sync_log_analyzer.py"
    spec = importlib.util.spec_from_file_location("sync_log_analyzer", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_checksum_mismatch_is_dominant_and_etag_framed():
    m = load()
    log = (
        "Transferred:   12 / 13, 92%\n"
        "Errors:         1\n"
        "2024/06/15 ERROR : big.bin: corrupted on transfer: md5 hash differ\n"
    )
    r = m.analyze(log)
    assert r["dominant_issue"] == "checksum_mismatch"
    assert r["stats"]["transferred"] == 12 and r["stats"]["errors"] == 1
    assert "ETag" in r["recommendation"]


def test_throttle_classified():
    m = load()
    r = m.analyze("ERROR : a: SlowDown (429)\nERROR : b: SlowDown\n")
    assert r["dominant_issue"] == "throttle"
    assert "concurrency" in r["recommendation"].lower()


def test_destructive_sync_flagged():
    m = load()
    r = m.analyze("rclone sync src: dst: --delete-during\nDeleted: 5\n")
    assert r["destructive_sync"] is True
    assert r["warnings"]


def test_clean_log_has_no_issue():
    m = load()
    r = m.analyze("Transferred: 100 / 100, 100%\nErrors: 0\n")
    assert r["dominant_issue"] is None
    assert r["destructive_sync"] is False
