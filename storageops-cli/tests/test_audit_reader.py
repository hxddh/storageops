"""Tests for audit_reader: list_sessions, get_session, compute_stats."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from storageops.audit_reader import list_sessions, get_session, compute_stats


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, records: list[dict]) -> None:
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _tmp() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    f.close()
    return Path(f.name)


class TestListSessions(unittest.TestCase):

    def test_empty_file(self):
        p = _tmp()
        p.write_text("")
        result = list_sessions(path=p)
        p.unlink()
        self.assertEqual(result, [])

    def test_missing_file(self):
        p = Path("/tmp/_audit_no_exist_test.jsonl")
        if p.exists():
            p.unlink()
        self.assertEqual(list_sessions(path=p), [])

    def test_single_session_fields(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "s1", "event": "session_start",
             "domain": "cli_sdk_behavior", "runtime": "pi"},
            {"ts": _ts(), "session": "s1", "event": "pi_result",
             "ok": True, "redaction_count": 2, "validation_ok": True, "event_count": 5},
            {"ts": _ts(), "session": "s1", "event": "tool_call",
             "turn": 1, "tool": "scan_secrets"},
            {"ts": _ts(), "session": "s1", "event": "session_end",
             "outcome": "success"},
        ])
        sessions = list_sessions(path=p)
        p.unlink()
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s["session_id"], "s1")
        self.assertEqual(s["domain"], "cli_sdk_behavior")
        self.assertEqual(s["runtime"], "pi")
        self.assertEqual(s["outcome"], "success")
        self.assertEqual(s["pi_ok"], True)
        self.assertEqual(s["redaction_count"], 2)
        self.assertEqual(s["event_count"], 5)
        self.assertIn("scan_secrets", s["tools"])

    def test_limit_respected(self):
        p = _tmp()
        rows = []
        for i in range(8):
            rows += [
                {"ts": _ts(), "session": f"s{i}", "event": "session_start",
                 "domain": "test", "runtime": "pi"},
                {"ts": _ts(), "session": f"s{i}", "event": "session_end",
                 "outcome": "success"},
            ]
        _write(p, rows)
        sessions = list_sessions(limit=3, path=p)
        p.unlink()
        self.assertLessEqual(len(sessions), 3)

    def test_in_progress_session_has_outcome(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "open", "event": "session_start",
             "domain": "test", "runtime": "pi"},
        ])
        sessions = list_sessions(path=p)
        p.unlink()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["outcome"], "in_progress")


class TestGetSession(unittest.TestCase):

    def test_returns_only_matching(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "aaa", "event": "session_start", "domain": "x"},
            {"ts": _ts(), "session": "bbb", "event": "session_start", "domain": "y"},
            {"ts": _ts(), "session": "aaa", "event": "session_end", "outcome": "success"},
        ])
        events = get_session("aaa", path=p)
        p.unlink()
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["session"] == "aaa" for e in events))

    def test_nonexistent_returns_empty(self):
        p = _tmp()
        _write(p, [{"ts": _ts(), "session": "aaa", "event": "session_start"}])
        result = get_session("zzz", path=p)
        p.unlink()
        self.assertEqual(result, [])


class TestComputeStats(unittest.TestCase):

    def test_empty(self):
        p = _tmp()
        p.write_text("")
        stats = compute_stats(path=p)
        p.unlink()
        self.assertEqual(stats["sessions"], 0)

    def test_pi_result_counts(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "s1", "event": "session_start",
             "domain": "cli_sdk_behavior", "runtime": "pi"},
            {"ts": _ts(), "session": "s1", "event": "pi_result",
             "ok": True, "redaction_count": 3, "validation_ok": True, "event_count": 7},
            {"ts": _ts(), "session": "s1", "event": "tool_call", "turn": 1, "tool": "scan_secrets"},
            {"ts": _ts(), "session": "s1", "event": "tool_call", "turn": 1, "tool": "scan_secrets"},
            {"ts": _ts(), "session": "s1", "event": "session_end", "outcome": "success"},
        ])
        stats = compute_stats(path=p)
        p.unlink()
        self.assertEqual(stats["sessions"], 1)
        self.assertEqual(stats["total_redactions"], 3)
        self.assertEqual(stats["total_pi_events"], 7)
        self.assertEqual(stats["pi_success_rate"], 1.0)
        self.assertEqual(stats["tool_frequency"].get("scan_secrets"), 2)
        self.assertEqual(stats["outcomes"].get("success"), 1)
        self.assertEqual(stats["domains"].get("cli_sdk_behavior"), 1)

    def test_pi_success_rate_none_when_no_pi_results(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "s1", "event": "session_start",
             "domain": "x", "runtime": "pi"},
        ])
        stats = compute_stats(path=p)
        p.unlink()
        self.assertIsNone(stats["pi_success_rate"])


if __name__ == "__main__":
    unittest.main()
