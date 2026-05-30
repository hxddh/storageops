"""Tests for the memory_store module."""
import sys
from pathlib import Path
from unittest import mock

# Ensure the CLI package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_store(tmp_path):
    """Return memory_store module patched to use a temp file."""
    import storageops.memory_store as ms
    tmp_file = tmp_path / "memory.jsonl"
    with mock.patch.object(ms, "_MEMORY_FILE", tmp_file):
        yield ms, tmp_file


def test_save_and_list(tmp_path):
    """save_case then list_cases returns the saved entry."""
    import storageops.memory_store as ms
    tmp_file = tmp_path / "memory.jsonl"
    with mock.patch.object(ms, "_MEMORY_FILE", tmp_file):
        ms.save_case("sess1", "cli_sdk_behavior", "multipart_etag_mismatch",
                     "rclone corrupted transfer due to ETag mismatch",
                     keywords=["rclone", "etag", "multipart"])
        results = ms.list_cases()
    assert len(results) == 1
    assert results[0]["root_cause"] == "multipart_etag_mismatch"
    assert results[0]["domain"] == "cli_sdk_behavior"


def test_search_returns_relevant(tmp_path):
    """search_cases ranks by keyword overlap."""
    import storageops.memory_store as ms
    tmp_file = tmp_path / "memory.jsonl"
    with mock.patch.object(ms, "_MEMORY_FILE", tmp_file):
        ms.save_case("s1", "cli_sdk_behavior", "etag_mismatch",
                     "rclone ETag checksum mismatch on multipart upload",
                     keywords=["rclone", "etag", "checksum"])
        ms.save_case("s2", "security_iam_policy", "cross_account_missing_iam",
                     "cross-account IAM allow missing",
                     keywords=["iam", "access", "denied", "cross-account"])
        results = ms.search_cases("rclone ETag mismatch multipart")
    assert len(results) >= 1
    assert results[0]["root_cause"] == "etag_mismatch"


def test_search_empty_when_no_overlap(tmp_path):
    """search_cases returns [] when no keyword overlap."""
    import storageops.memory_store as ms
    tmp_file = tmp_path / "memory.jsonl"
    with mock.patch.object(ms, "_MEMORY_FILE", tmp_file):
        ms.save_case("s1", "lifecycle_cost", "small_file_ia_penalty",
                     "small files in STANDARD_IA with min-size billing",
                     keywords=["lifecycle", "ia", "cost"])
        results = ms.search_cases("rclone ETag mismatch")
    assert results == []


def test_search_domain_filter(tmp_path):
    """search_cases domain filter excludes non-matching domains."""
    import storageops.memory_store as ms
    tmp_file = tmp_path / "memory.jsonl"
    with mock.patch.object(ms, "_MEMORY_FILE", tmp_file):
        ms.save_case("s1", "cli_sdk_behavior", "etag_mismatch",
                     "rclone ETag mismatch", keywords=["rclone", "etag"])
        ms.save_case("s2", "security_iam_policy", "access_denied",
                     "rclone AccessDenied IAM", keywords=["rclone", "iam"])
        results = ms.search_cases("rclone", domain="cli_sdk_behavior")
    assert all(r["domain"] == "cli_sdk_behavior" for r in results)


def test_list_empty_file(tmp_path):
    """list_cases returns [] when no memory file exists."""
    import storageops.memory_store as ms
    tmp_file = tmp_path / "nonexistent.jsonl"
    with mock.patch.object(ms, "_MEMORY_FILE", tmp_file):
        results = ms.list_cases()
    assert results == []


def test_summary_truncated(tmp_path):
    """save_case truncates long summaries to _MAX_SUMMARY_LEN."""
    import storageops.memory_store as ms
    tmp_file = tmp_path / "memory.jsonl"
    long_summary = "x" * 1000
    with mock.patch.object(ms, "_MEMORY_FILE", tmp_file):
        entry = ms.save_case("s1", "cli_sdk_behavior", "test", long_summary)
    assert len(entry["summary"]) <= ms._MAX_SUMMARY_LEN
