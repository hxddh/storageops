from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from storageops.report_validator import validate_agent_report
from storageops.runtime import AgentRunOptions, PiRpcRuntime
from storageops.runtime.pi_rpc import build_pi_prompt, reconstruct_report_from_events, redact_for_pi

VALID_REPORT = """---
category: security_iam_policy
root_cause_type: permission_denied
confidence: 0.8
severity: medium
---

## Summary

The operation was denied.

## Key Evidence

- Evidence from the redacted log shows AccessDenied.

## Root Cause Ranking

1. Missing permission.

## Verification Plan

- Run `storageops triage <file>` on the redacted evidence.

## Remediation

- Adjust policy only after human review; any mutation is manual-only.

## Safety Notes

- Offline evidence only.

## Limitations

- No live cloud calls were made.
"""


def _fake_pi(tmp_path: Path, body: str, sleep: float = 0, deltas: list[str] | None = None) -> Path:
    script = tmp_path / "fake-pi.py"
    delta_lines = ""
    for delta in deltas or []:
        delta_lines += f"print(json.dumps({{'type':'delta','text':{delta!r}}}), flush=True)\n"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, time\n"
        "req=json.loads(sys.stdin.readline())\n"
        f"time.sleep({sleep!r})\n"
        "print(json.dumps({'type':'request_seen','prompt':req.get('prompt','')}), flush=True)\n"
        f"{delta_lines}"
        f"print(json.dumps({{'type':'final_report','markdown':{body!r}}}), flush=True)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_agent_uses_pi_runtime_by_default_with_fake_process(tmp_path: Path):
    evidence = tmp_path / "input.log"
    secret = "AKIAIOSFODNN7EXAMPLE"
    evidence.write_text(f"AccessDenied with {secret}\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz\n")
    fake_pi = _fake_pi(tmp_path, VALID_REPORT)

    result = PiRpcRuntime(
        AgentRunOptions(pi_command=str(fake_pi), timeout_seconds=5)
    ).run(evidence)

    assert result.ok
    assert result.runtime == "pi"
    assert "## Key Evidence" in result.report_markdown
    serialized_events = json.dumps(result.raw_events)
    assert secret not in serialized_events
    assert secret not in result.report_markdown


def test_agent_runtime_pi_explicit_via_cli_fake_process(tmp_path: Path):
    evidence = tmp_path / "input.log"
    evidence.write_text("AccessDenied\n")
    fake_pi = _fake_pi(tmp_path, VALID_REPORT)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "storageops.cli",
            "agent",
            str(evidence),
            "--runtime",
            "pi",
            "--pi-command",
            str(fake_pi),
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )
    assert proc.returncode == 0, proc.stderr
    assert "## Key Evidence" in proc.stdout


def test_missing_pi_binary_returns_helpful_error(tmp_path: Path):
    evidence = tmp_path / "input.log"
    evidence.write_text("AccessDenied\n")
    result = PiRpcRuntime(AgentRunOptions(pi_command="definitely-missing-pi-binary")).run(evidence)
    assert not result.ok
    assert "Pi Coding Agent is required" in result.error


def test_pi_timeout_returns_structured_failure(tmp_path: Path):
    evidence = tmp_path / "input.log"
    evidence.write_text("AccessDenied\n")
    fake_pi = _fake_pi(tmp_path, VALID_REPORT, sleep=2)
    result = PiRpcRuntime(AgentRunOptions(pi_command=str(fake_pi), timeout_seconds=1)).run(evidence)
    assert not result.ok
    assert "timed out" in result.error


def test_event_parser_reconstructs_final_markdown():
    assert reconstruct_report_from_events([
        {"type": "delta", "text": "hel"},
        {"type": "delta", "text": "lo"},
    ]) == "hello"
    assert reconstruct_report_from_events([
        {"type": "delta", "text": "draft"},
        {"type": "final_report", "markdown": "final"},
    ]) == "final"


def test_raw_secrets_never_reach_pi_prompt_or_redacted_evidence(tmp_path: Path):
    secret = "AKIAIOSFODNN7EXAMPLE"
    redacted, count = redact_for_pi(f"access_key_id={secret}\n")
    redacted_file = tmp_path / "redacted.txt"
    redacted_file.write_text(redacted)
    prompt = build_pi_prompt(
        evidence_file=redacted_file,
        original_filename="raw.log",
        redaction_count=count,
        max_turns=8,
    )
    assert secret not in prompt
    assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_unsafe_pi_output_is_rejected():
    text = VALID_REPORT.replace("## Remediation\n\n- Adjust policy only after human review; any mutation is manual-only.", "## Remediation\n\n- delete the bucket")
    result = validate_agent_report(text)
    assert not result["valid"]
    assert any("manual-only" in err for err in result["errors"])


def test_missing_evidence_section_rejected():
    text = VALID_REPORT.replace("## Key Evidence", "## Observations")
    result = validate_agent_report(text)
    assert not result["valid"]
    assert any("evidence section" in err for err in result["errors"])


def test_old_llm_flags_fail_with_migration_guidance(tmp_path: Path):
    evidence = tmp_path / "input.log"
    evidence.write_text("AccessDenied\n")
    proc = subprocess.run(
        [sys.executable, "-m", "storageops.cli", "agent", str(evidence), "--llm-provider", "openai"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )
    assert proc.returncode == 2
    assert "StorageOps no longer manages LLM providers" in proc.stderr


@pytest.mark.parametrize(
    "command",
    [
        "aws s3api delete-bucket --bucket prod",
        "aws s3api delete-object --bucket prod --key important.txt",
        "delete-bucket --bucket prod",
        "delete-object --bucket prod --key important.txt",
        "aws s3 rm s3://prod/important.txt",
        "rm s3://prod/important.txt",
        "rm --recursive s3://prod/prefix/",
        "s3cmd del s3://prod/important.txt",
        "s5cmd rm s3://prod/important.txt",
        "mc rm alias/prod/important.txt",
        "rclone purge s3:prod/prefix",
    ],
)
def test_destructive_s3_delete_commands_require_manual_only(command: str):
    text = VALID_REPORT.replace(
        "## Remediation\n\n- Adjust policy only after human review; any mutation is manual-only.",
        f"## Remediation\n\n- `{command}`",
    )

    result = validate_agent_report(text)

    assert not result["valid"]
    assert any("manual-only" in err for err in result["errors"])


def test_destructive_s3_delete_commands_allowed_when_manual_only():
    text = VALID_REPORT.replace(
        "## Remediation\n\n- Adjust policy only after human review; any mutation is manual-only.",
        "## Remediation\n\n- manual-only: `aws s3api delete-bucket --bucket prod`",
    )

    result = validate_agent_report(text)

    assert result["valid"]


def test_cli_stream_does_not_print_reconstructed_report_twice(tmp_path: Path):
    evidence = tmp_path / "input.log"
    evidence.write_text("AccessDenied\n")
    midpoint = len(VALID_REPORT) // 2
    fake_pi = _fake_pi(tmp_path, VALID_REPORT, deltas=[VALID_REPORT[:midpoint], VALID_REPORT[midpoint:]])

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "storageops.cli",
            "agent",
            str(evidence),
            "--runtime",
            "pi",
            "--pi-command",
            str(fake_pi),
            "--stream",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == VALID_REPORT
    assert proc.stdout.count("## Key Evidence") == 1
