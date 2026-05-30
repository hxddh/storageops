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
        p = _tmp(); p.write_text(""); result = list_sessions(path=p); p.unlink()
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
             "domain": "cli_sdk_behavior", "provider": "anthropic/claude-opus-4-8"},
            {"ts": _ts(), "session": "s1", "event": "llm_call", "turn": 1,
             "provider": "anthropic", "model": "claude-opus-4-8",
             "input_tokens": 800, "output_tokens": 150, "stop_reason": "end_turn"},
            {"ts": _ts(), "session": "s1", "event": "tool_call",
             "turn": 1, "tool": "scan_secrets"},
            {"ts": _ts(), "session": "s1", "event": "session_end",
             "turns_used": 2, "outcome": "success"},
        ])
        sessions = list_sessions(path=p); p.unlink()
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s["session_id"], "s1")
        self.assertEqual(s["domain"], "cli_sdk_behavior")
        self.assertEqual(s["outcome"], "success")
        self.assertEqual(s["input_tokens"], 800)
        self.assertEqual(s["output_tokens"], 150)
        self.assertIn("scan_secrets", s["tools"])

    def test_limit_respected(self):
        p = _tmp()
        rows = []
        for i in range(8):
            rows += [
                {"ts": _ts(), "session": f"s{i}", "event": "session_start",
                 "domain": "test", "provider": "mock"},
                {"ts": _ts(), "session": f"s{i}", "event": "session_end",
                 "turns_used": 1, "outcome": "success"},
            ]
        _write(p, rows)
        sessions = list_sessions(limit=3, path=p); p.unlink()
        self.assertLessEqual(len(sessions), 3)

    def test_in_progress_session_has_outcome(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "open", "event": "session_start",
             "domain": "test", "provider": "mock"},
        ])
        sessions = list_sessions(path=p); p.unlink()
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
        events = get_session("aaa", path=p); p.unlink()
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["session"] == "aaa" for e in events))

    def test_nonexistent_returns_empty(self):
        p = _tmp()
        _write(p, [{"ts": _ts(), "session": "aaa", "event": "session_start"}])
        self.assertEqual(get_session("zzz", path=p), []); p.unlink()


class TestComputeStats(unittest.TestCase):

    def test_empty(self):
        p = _tmp(); p.write_text("")
        stats = compute_stats(path=p); p.unlink()
        self.assertEqual(stats["sessions"], 0)
        self.assertEqual(stats["total_tokens"], 0)

    def test_token_counts(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "s1", "event": "session_start",
             "domain": "cli_sdk_behavior", "provider": "mock"},
            {"ts": _ts(), "session": "s1", "event": "llm_call", "turn": 1,
             "provider": "anthropic", "model": "m",
             "input_tokens": 500, "output_tokens": 100, "stop_reason": "end_turn"},
            {"ts": _ts(), "session": "s1", "event": "tool_call", "turn": 1, "tool": "scan_secrets"},
            {"ts": _ts(), "session": "s1", "event": "tool_call", "turn": 1, "tool": "scan_secrets"},
            {"ts": _ts(), "session": "s1", "event": "critique_turn", "turn": 2, "confirmed": True},
            {"ts": _ts(), "session": "s1", "event": "session_end",
             "turns_used": 2, "outcome": "success"},
        ])
        stats = compute_stats(path=p); p.unlink()
        self.assertEqual(stats["sessions"], 1)
        self.assertEqual(stats["total_input_tokens"], 500)
        self.assertEqual(stats["total_output_tokens"], 100)
        self.assertEqual(stats["total_tokens"], 600)
        self.assertEqual(stats["tool_frequency"].get("scan_secrets"), 2)
        self.assertEqual(stats["critique_confirmation_rate"], 1.0)
        self.assertEqual(stats["outcomes"].get("success"), 1)
        self.assertEqual(stats["domains"].get("cli_sdk_behavior"), 1)

    def test_critique_confirmation_rate_none_when_no_critiques(self):
        p = _tmp()
        _write(p, [
            {"ts": _ts(), "session": "s1", "event": "session_start",
             "domain": "x", "provider": "mock"},
        ])
        stats = compute_stats(path=p); p.unlink()
        self.assertIsNone(stats["critique_confirmation_rate"])


if __name__ == "__main__":
    unittest.main()
