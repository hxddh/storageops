"""
Integration tests for the LLM agent loop using a mock LLM provider.

These tests exercise the full ReAct loop without making real API calls.
The mock provider returns scripted LLMResponse sequences.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_CLI_DIR = Path(__file__).parent.parent
_CORE_DIR = _CLI_DIR.parent.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from storageops.llm_agent import run_llm_agent
from storageops.llm_provider import LLMResponse


class MockProvider:
    """Scripted LLM provider — returns pre-defined responses in sequence."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._idx = 0
        self.model = "mock/test"
        self.calls: list[dict] = []

    def complete(self, messages, tools=None, system="", max_tokens=4096, on_text_chunk=None):
        if self._idx >= len(self._responses):
            raise RuntimeError(f"MockProvider exhausted after {self._idx} calls")
        resp = self._responses[self._idx]
        self._idx += 1
        self.calls.append({"messages": messages, "tools": tools})
        if on_text_chunk and resp.content:
            on_text_chunk(resp.content)
        return resp


def _report(root_cause: str = "test_root_cause") -> str:
    return f"""\
---
category: cli_sdk_behavior
root_cause_type: {root_cause}
confidence: 0.85
severity: medium
---

## Summary

Test diagnostic summary for {root_cause}.

## Key Evidence

Evidence found in log.

## Remediation

Apply the recommended fix.
"""


class TestReActLoop(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._mem = Path(self._tmp) / "memory.jsonl"
        self._audit = Path(self._tmp) / "audit.jsonl"

    def _patches(self):
        import storageops.memory_store as ms
        import storageops.audit_logger as al
        return [
            patch.object(ms, "_MEMORY_FILE", self._mem),
            patch.object(al, "_AUDIT_FILE", self._audit),
            patch.object(al, "_AUDIT_DIR", Path(self._tmp)),
        ]

    def _run(self, provider, **kwargs):
        patches = self._patches()
        for p in patches:
            p.start()
        kwargs.setdefault("max_turns", 8)
        try:
            with patch("storageops.llm_agent.build_provider", return_value=provider):
                return run_llm_agent(provider_name="mock", **kwargs)
        finally:
            for p in patches:
                p.stop()

    def test_tool_then_answer_then_critique_confirmed(self):
        """Full ReAct: tool call → result → answer → critique confirmed → memory saved."""
        provider = MockProvider([
            LLMResponse(
                content="Scanning first.",
                stop_reason="tool_use",
                tool_calls=[{"id": "tc1", "name": "scan_secrets",
                              "input": {"text": "rclone log"}}],
                input_tokens=100, output_tokens=30,
            ),
            LLMResponse(
                content=_report("multipart_etag_mismatch"),
                stop_reason="end_turn",
                input_tokens=200, output_tokens=300,
            ),
            LLMResponse(
                content="CONFIRMED: multipart ETag mismatch is the root cause.",
                stop_reason="end_turn",
                input_tokens=50, output_tokens=20,
            ),
        ])

        result = self._run(
            provider,
            evidence_text="rclone v1.60 log with corrupted on transfer",
            domain="cli_sdk_behavior",
        )

        self.assertTrue(result["ok"])
        self.assertIn("scan_secrets", result["tool_calls_made"])
        self.assertEqual(result["root_cause"], "multipart_etag_mismatch")
        # Memory entry written
        self.assertTrue(self._mem.exists())
        entry = json.loads(self._mem.read_text())
        self.assertEqual(entry["domain"], "cli_sdk_behavior")
        self.assertEqual(entry["root_cause"], "multipart_etag_mismatch")

    def test_critique_revises_answer(self):
        """Critique that does NOT start with CONFIRMED: replaces the initial answer."""
        provider = MockProvider([
            LLMResponse(
                content=_report("unknown"),
                stop_reason="end_turn",
                input_tokens=100, output_tokens=200,
            ),
            LLMResponse(
                content=_report("clock_skew"),   # revised — no CONFIRMED: prefix
                stop_reason="end_turn",
                input_tokens=50, output_tokens=100,
            ),
        ])

        result = self._run(
            provider,
            evidence_text="SignatureDoesNotMatch error",
            domain="s3_protocol_compatibility",
        )

        self.assertTrue(result["ok"])
        self.assertIn("clock_skew", result["report"])
        self.assertEqual(result["root_cause"], "clock_skew")

    def test_unsafe_output_blocked(self):
        """Response containing unsafe pattern → ok=False, error=unsafe_output_blocked."""
        provider = MockProvider([
            LLMResponse(
                content="You should delete the bucket to start fresh.",
                stop_reason="end_turn",
                input_tokens=100, output_tokens=50,
            ),
        ])

        result = self._run(
            provider,
            evidence_text="some evidence",
            domain="lifecycle_cost",
            max_turns=1,  # suppress critique turn
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "unsafe_output_blocked")

    def test_secret_redacted_from_input(self):
        """AKIA key in input is redacted before the first LLM message is built."""
        provider = MockProvider([
            LLMResponse(
                content=_report("test"),
                stop_reason="end_turn",
                input_tokens=100, output_tokens=200,
            ),
            LLMResponse(
                content="CONFIRMED: test",
                stop_reason="end_turn",
                input_tokens=30, output_tokens=10,
            ),
        ])

        result = self._run(
            provider,
            evidence_text="AKIAIOSFODNN7EXAMPLE is the access key in this log",
            domain="security_iam_policy",
        )

        self.assertTrue(result["ok"])
        self.assertGreater(result["secrets_redacted"], 0)
        # AKIA key must not appear in the messages sent to the LLM
        first_msg_text = str(provider.calls[0]["messages"])
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", first_msg_text)

    def test_max_turns_reached(self):
        """Looping tool calls until max_turns → ok=False, error=max_turns_reached."""
        forever_tool = LLMResponse(
            content="",
            stop_reason="tool_use",
            tool_calls=[{"id": "tc1", "name": "scan_secrets",
                         "input": {"text": "x"}}],
            input_tokens=50, output_tokens=20,
        )
        provider = MockProvider([forever_tool] * 10)

        result = self._run(
            provider,
            evidence_text="evidence",
            domain="cli_sdk_behavior",
            max_turns=3,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "max_turns_reached")

    def test_tool_result_fed_back_to_llm(self):
        """Tool result appears as tool_result message in the second LLM call."""
        provider = MockProvider([
            LLMResponse(
                content="",
                stop_reason="tool_use",
                tool_calls=[{"id": "tc_lc", "name": "parse_lifecycle_xml",
                              "input": {"xml_text": "<LifecycleConfiguration/>"}}],
                input_tokens=100, output_tokens=30,
            ),
            LLMResponse(
                content=_report("small_object_ia"),
                stop_reason="end_turn",
                input_tokens=200, output_tokens=200,
            ),
            LLMResponse(
                content="CONFIRMED: small object IA penalty",
                stop_reason="end_turn",
                input_tokens=50, output_tokens=10,
            ),
        ])

        result = self._run(
            provider,
            evidence_text="lifecycle configuration",
            domain="lifecycle_cost",
        )

        self.assertTrue(result["ok"])
        self.assertIn("parse_lifecycle_xml", result["tool_calls_made"])
        # Second call must include tool_result in messages
        second_msgs = provider.calls[1]["messages"]
        tool_result_present = any(
            isinstance(m.get("content"), list)
            and any(c.get("type") == "tool_result" for c in m["content"])
            for m in second_msgs
        )
        self.assertTrue(tool_result_present, "tool result not found in second LLM call messages")

    def test_session_id_in_result(self):
        """Result always contains a session_id (used for memory + audit correlation)."""
        provider = MockProvider([
            LLMResponse(
                content=_report("test"),
                stop_reason="end_turn",
                input_tokens=50, output_tokens=100,
            ),
            LLMResponse(
                content="CONFIRMED: test",
                stop_reason="end_turn",
                input_tokens=20, output_tokens=10,
            ),
        ])

        result = self._run(
            provider,
            evidence_text="evidence",
            domain="cli_sdk_behavior",
        )

        self.assertIn("session_id", result)
        self.assertIsInstance(result["session_id"], str)
        self.assertGreater(len(result["session_id"]), 0)

    def test_report_validation_in_result(self):
        """Valid YAML frontmatter → report_valid=True returned in result."""
        provider = MockProvider([
            LLMResponse(
                content=_report("test_root_cause"),
                stop_reason="end_turn",
                input_tokens=50, output_tokens=100,
            ),
            LLMResponse(
                content="CONFIRMED: test",
                stop_reason="end_turn",
                input_tokens=20, output_tokens=10,
            ),
        ])

        result = self._run(
            provider,
            evidence_text="rclone log",
            domain="cli_sdk_behavior",
        )

        self.assertTrue(result["ok"])
        self.assertIn("report_valid", result)
        self.assertTrue(result["report_valid"])


if __name__ == "__main__":
    unittest.main()
