"""Pi Coding Agent JSONL RPC runtime for StorageOps."""
from __future__ import annotations

import json
import os
import re
import subprocess
import select
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from storageops.audit_logger import log_session_start, log_pi_result, log_session_end
from storageops.config import get_pi_command as _cfg_pi_command
from storageops.config import get_workdir as _cfg_workdir
from storageops.config import get_skills_dir as _cfg_skills_dir
from storageops.config import get_api_key as _cfg_api_key
from storageops.config import get_provider as _cfg_provider
from storageops.report_validator import validate_agent_report
from storageops.runtime.base import AgentRunOptions, AgentRunResult

from secret_scanner import scan as _scan_secrets


def _pi_workdir() -> Path:
    """Return the directory Pi should run in (contains .pi/settings.json)."""
    d = _cfg_workdir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _skills_path() -> str:
    """Return skills path for the Pi RPC request."""
    d = _cfg_skills_dir()
    if d and d.exists():
        return str(d)
    # Fallback: repo layout for editable installs
    repo = Path(__file__).resolve().parents[3] / "agents" / "skills"
    if repo.exists():
        return str(repo)
    return "./agents/skills"


_PI_NOT_FOUND_MSG = """\
Pi Agent not found on PATH.

  Pi Agent is required for `storageops diagnose`.
  Install Pi Agent, then run: storageops setup

  Offline commands (no Pi required):
    storageops triage <log>
    storageops analyze <domain> <log>\
"""

_MIGRATION_ERROR = (
    "StorageOps no longer manages LLM providers. Configure providers and models "
    "in Pi Coding Agent."
)

_ADDITIONAL_SECRET_PATTERNS = [
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bA3T[A-Z0-9]{16}\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)(cookie|set-cookie):\s*.*?(?=\n|$)"),
    re.compile(r"(?i)(x-amz-security-token|session[_-]?token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(api[_-]?key|apikey|provider[_-]?api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(X-Amz-Credential|X-Amz-Signature|X-Amz-Security-Token)=[^\s&]+"),
    re.compile(r"(?i)(secret_access_key|aws_secret_access_key)\s*[:=]\s*\S+"),
]


def redact_for_pi(text: str) -> tuple[str, int]:
    """Apply StorageOps redaction plus extra provider/API-token patterns."""
    result = _scan_secrets(text)
    redacted = result["redacted_text"]
    extra_count = 0
    for pattern in _ADDITIONAL_SECRET_PATTERNS:
        redacted, count = pattern.subn("[REDACTED]", redacted)
        extra_count += count
    return redacted, int(result.get("count", 0)) + extra_count


def _load_prompt_template() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "pi_diagnosis_prompt.md").read_text(
        encoding="utf-8"
    )


def build_pi_prompt(
    *, evidence_file: Path, original_filename: str, redaction_count: int, max_turns: int
) -> str:
    """Build the StorageOps prompt sent to Pi. It contains no raw evidence content."""
    prompt = _load_prompt_template()
    replacements = {
        "{{ evidence_file }}": str(evidence_file),
        "{{ original_filename }}": original_filename,
        "{{ redaction_count }}": str(redaction_count),
        "{{ max_turns }}": str(max_turns),
    }
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)
    return prompt


def _safe_event(event: dict[str, Any]) -> dict[str, Any]:
    """Redact string payloads in captured raw events before returning them."""
    safe: dict[str, Any] = {}
    for key, value in event.items():
        if isinstance(value, str):
            safe[key] = redact_for_pi(value)[0]
        elif isinstance(value, dict):
            safe[key] = _safe_event(value)
        elif isinstance(value, list):
            safe[key] = [
                _safe_event(v) if isinstance(v, dict)
                else redact_for_pi(v)[0] if isinstance(v, str)
                else v
                for v in value
            ]
        else:
            safe[key] = value
    return safe


def _extract_text(event: dict[str, Any]) -> str:
    for key in ("markdown", "report_markdown", "final_report", "content", "text", "delta"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    data = event.get("data")
    if isinstance(data, dict):
        return _extract_text(data)
    return ""


def _event_is_final(event: dict[str, Any]) -> bool:
    typ = str(event.get("type") or event.get("event") or "").lower()
    return typ in {"final", "final_report", "report", "done", "complete", "completed"}


def reconstruct_report_from_events(events: list[dict[str, Any]]) -> str:
    """Reconstruct final markdown from flexible Pi JSONL event shapes."""
    final = ""
    chunks: list[str] = []
    for event in events:
        text = _extract_text(event)
        typ = str(event.get("type") or event.get("event") or "").lower()
        if _event_is_final(event) and text:
            final = text
        elif typ in {"delta", "content_delta", "message_delta", "token", "text"} and text:
            chunks.append(text)
    return final or "".join(chunks)


class PiRpcRuntime:
    """Run Pi Coding Agent in JSONL RPC mode."""

    runtime_name = "pi"

    def __init__(self, options: AgentRunOptions | None = None):
        self.options = options or AgentRunOptions()

    def run(self, input_file: str | os.PathLike[str]) -> AgentRunResult:
        import uuid
        session_id = str(uuid.uuid4())[:8]

        input_path = Path(input_file)
        if not input_path.exists():
            return AgentRunResult(False, self.runtime_name, error=f"File not found: {input_file}")

        raw_text = input_path.read_text(encoding="utf-8", errors="replace")
        redacted_text, redaction_count = redact_for_pi(raw_text)

        from storageops.agent import classify_evidence
        domain = classify_evidence(redacted_text).get("primary_domain", "unknown")
        log_session_start(session_id, domain, runtime="pi")

        with tempfile.TemporaryDirectory(prefix="storageops-pi-") as tmpdir:
            evidence_path = Path(tmpdir) / "redacted-evidence.txt"
            evidence_path.write_text(redacted_text, encoding="utf-8")
            prompt = build_pi_prompt(
                evidence_file=evidence_path,
                original_filename=input_path.name,
                redaction_count=redaction_count,
                max_turns=self.options.max_turns,
            )
            prompt = redact_for_pi(prompt)[0]

            request: dict[str, Any] = {
                "type": "diagnose",
                "runtime": "storageops",
                "prompt": prompt,
                "evidence_file": str(evidence_path),
                "skills_path": _skills_path(),
                "max_turns": self.options.max_turns,
                "stream": self.options.stream,
            }
            if self.options.pi_model:
                request["model"] = self.options.pi_model
            if self.options.pi_provider:
                request["provider"] = self.options.pi_provider

            result = self._run_rpc(request)
            log_pi_result(
                session_id,
                ok=result.ok,
                redaction_count=redaction_count,
                validation_ok=result.ok,
                event_count=len(result.raw_events),
            )
            log_session_end(session_id, "success" if result.ok else "failed")
            return result

    def _command(self) -> list[str]:
        cmd = [self.options.pi_command, "--mode", "rpc"]
        if self.options.pi_model:
            cmd.extend(["--model", self.options.pi_model])
        if self.options.pi_provider:
            cmd.extend(["--provider", self.options.pi_provider])
        return cmd

    def _pi_env(self) -> dict:
        """Build subprocess environment: inherit + inject LLM API key."""
        env = os.environ.copy()
        api_key = _cfg_api_key()
        if api_key:
            provider = _cfg_provider()
            env_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai":    "OPENAI_API_KEY",
            }
            env_var = env_map.get(provider, f"{provider.upper()}_API_KEY")
            env.setdefault(env_var, api_key)
        return env

    def _run_rpc(self, request: dict[str, Any]) -> AgentRunResult:
        try:
            proc = subprocess.Popen(
                self._command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(_pi_workdir()),
                env=self._pi_env(),
            )
        except FileNotFoundError:
            return AgentRunResult(False, self.runtime_name, error=_PI_NOT_FOUND_MSG)
        except OSError as exc:
            return AgentRunResult(False, self.runtime_name, error=f"Failed to start Pi: {exc}")

        assert proc.stdin is not None
        assert proc.stdout is not None
        deadline = time.monotonic() + self.options.timeout_seconds
        events: list[dict[str, Any]] = []
        saw_final = False

        try:
            proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            proc.stdin.close()

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    return AgentRunResult(
                        False,
                        self.runtime_name,
                        raw_events=events,
                        error=f"Pi RPC timed out after {self.options.timeout_seconds} seconds",
                    )
                ready, _, _ = select.select([proc.stdout], [], [], min(0.1, remaining))
                if not ready:
                    if proc.poll() is not None:
                        break
                    continue
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "stderr", "text": line.strip()}
                safe = _safe_event(event)
                events.append(safe)
                if self.options.event_callback:
                    try:
                        self.options.event_callback(safe)
                    except Exception:
                        pass
                if self.options.stream:
                    chunk = _extract_text(safe)
                    typ = str(safe.get("type") or safe.get("event") or "").lower()
                    if chunk and typ in {"delta", "content_delta", "message_delta", "token", "text"}:
                        print(chunk, end="", flush=True)
                if _event_is_final(event):
                    saw_final = True
                    break

            stderr = ""
            if not saw_final:
                try:
                    _, stderr = proc.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    _, stderr = proc.communicate()

                if proc.returncode not in (0, None):
                    err = redact_for_pi(stderr or "Pi RPC failed")[0]
                    return AgentRunResult(False, self.runtime_name, raw_events=events, error=err)

            report = reconstruct_report_from_events(events)
            validation = validate_agent_report(report)
            if not validation["valid"]:
                return AgentRunResult(
                    False,
                    self.runtime_name,
                    raw_events=events,
                    error="Report validation failed: " + "; ".join(validation["errors"]),
                )
            if report:
                try:
                    fm_cat = re.search(r"^category:\s*(\S+)", report, re.MULTILINE)
                    fm_rc = re.search(r"^root_cause_type:\s*(\S+)", report, re.MULTILINE)
                    if fm_cat and fm_rc:
                        from storageops.memory_store import save_case
                        save_case(
                            session_id,
                            fm_cat.group(1),
                            fm_rc.group(1),
                            report[:400],
                            keywords=[],
                        )
                except Exception:
                    pass
            return AgentRunResult(True, self.runtime_name, report_markdown=report, raw_events=events)
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass


__all__ = [
    "PiRpcRuntime",
    "redact_for_pi",
    "build_pi_prompt",
    "reconstruct_report_from_events",
    "_MIGRATION_ERROR",
]
