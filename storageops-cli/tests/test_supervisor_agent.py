"""Tests for supervisor_agent: triage, tool filtering, and routing logic."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_CLI_DIR = Path(__file__).parent.parent
_CORE_DIR = _CLI_DIR.parent.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from storageops.supervisor_agent import run_supervisor_agent, _triage, _filter_tools


def _ok(domain: str, root_cause: str = "test") -> dict:
    return {
        "ok": True,
        "report": (
            f"---\ncategory: {domain}\nroot_cause_type: {root_cause}\n"
            "confidence: 0.8\nseverity: medium\n---\n\n## Summary\nTest."
        ),
        "domain": domain,
        "root_cause": root_cause,
        "turns_used": 2,
        "session_id": "test1234",
        "tool_calls_made": [],
        "secrets_redacted": 0,
    }


class TestTriage(unittest.TestCase):

    def test_detects_sigv4_domain(self):
        domains = _triage("SignatureDoesNotMatch CanonicalRequest StringToSign")
        names = [d["domain"] for d in domains]
        self.assertIn("s3_protocol_compatibility", names)

    def test_detects_throttling(self):
        domains = _triage("SlowDown: reduce request rate. 429 ThrottlingException")
        names = [d["domain"] for d in domains]
        self.assertIn("performance_throughput", names)

    def test_empty_text_returns_empty(self):
        self.assertEqual(_triage(""), [])

    def test_results_sorted_descending(self):
        domains = _triage("SlowDown 429 ThrottlingException throughput AccessDenied")
        if len(domains) > 1:
            self.assertGreaterEqual(domains[0]["confidence"], domains[1]["confidence"])

    def test_confidence_capped_at_0_95(self):
        text = "SignatureDoesNotMatch InvalidSignature CanonicalRequest StringToSign"
        for d in _triage(text):
            self.assertLessEqual(d["confidence"], 0.95)

    def test_no_false_positive_on_unrelated_text(self):
        domains = _triage("the quick brown fox jumps over the lazy dog")
        self.assertEqual(domains, [])


class TestFilterTools(unittest.TestCase):

    def test_keeps_only_allowed(self):
        tools = [{"name": "scan_secrets"}, {"name": "parse_rclone_log"}, {"name": "analyze_policy"}]
        result = _filter_tools(tools, ["scan_secrets", "analyze_policy"])
        names = {t["name"] for t in result}
        self.assertEqual(names, {"scan_secrets", "analyze_policy"})

    def test_empty_allowed_returns_empty(self):
        tools = [{"name": "scan_secrets"}]
        self.assertEqual(_filter_tools(tools, []), [])

    def test_unknown_tool_names_ignored(self):
        tools = [{"name": "scan_secrets"}]
        result = _filter_tools(tools, ["scan_secrets", "nonexistent_tool"])
        self.assertEqual(len(result), 1)


class TestRunSupervisorAgent(unittest.TestCase):

    def _run(self, text: str, mock_results: list[dict], **kwargs) -> dict:
        it = iter(mock_results)
        with patch("storageops.llm_agent.run_llm_agent", side_effect=lambda **kw: next(it)):
            return run_supervisor_agent(
                evidence_text=text,
                provider_name="mock",
                **kwargs,
            )

    def test_primary_domain_in_routing(self):
        text = "SignatureDoesNotMatch CanonicalRequest StringToSign"
        result = self._run(text, [_ok("s3_protocol_compatibility")])
        self.assertTrue(result["ok"])
        self.assertEqual(result["routing"]["primary"], "s3_protocol_compatibility")

    def test_all_domains_list_returned(self):
        text = "SignatureDoesNotMatch AccessDenied 403 SlowDown"
        result = self._run(text, [_ok("s3_protocol_compatibility")])
        self.assertIn("all_domains", result)
        self.assertIsInstance(result["all_domains"], list)

    def test_triage_scores_in_routing(self):
        text = "SlowDown 429 throughput MB/s AccessDenied"
        result = self._run(text, [_ok("performance_throughput")])
        self.assertIn("triage_scores", result["routing"])
        self.assertIsInstance(result["routing"]["triage_scores"], dict)

    def test_unknown_domain_when_no_match(self):
        text = "the quick brown fox"
        result = self._run(text, [_ok("unknown")])
        self.assertEqual(result["routing"]["primary"], "unknown")
        self.assertEqual(result["routing"]["secondary"], [])

    def test_secondary_not_spawned_when_primary_fails(self):
        # If primary returns ok=False, secondary should not run
        text = "SlowDown 429 AccessDenied 403 IAM policy"
        primary_fail = {**_ok("performance_throughput"), "ok": False, "error": "test_error"}
        call_count = [0]
        def mock_llm(**kw):
            call_count[0] += 1
            return primary_fail
        with patch("storageops.llm_agent.run_llm_agent", side_effect=mock_llm):
            result = run_supervisor_agent(
                evidence_text=text, provider_name="mock"
            )
        # Secondary should NOT have been called (primary failed)
        self.assertEqual(call_count[0], 1)
        self.assertNotIn("secondary_report", result)


if __name__ == "__main__":
    unittest.main()
