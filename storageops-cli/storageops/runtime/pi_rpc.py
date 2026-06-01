"""Pi Coding Agent JSONL RPC runtime for StorageOps."""
from __future__ import annotations

import json
import os
import re
import subprocess
import select
import tempfile
import time
from pathlib import Path
from typing import Any

from storageops.audit_logger import log_session_start, log_pi_result, log_session_end
from storageops.config import get_workdir as _cfg_workdir
from storageops.config import get_skills_dir as _cfg_skills_dir
from storageops.config import get_api_key as _cfg_api_key
from storageops.config import get_provider as _cfg_provider
from storageops.report_validator import safety_lint
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


def _load_prompt() -> str:
    """Load the single StorageOps identity prompt template."""
    prompt_dir = Path(__file__).resolve().parents[1] / "prompts"
    path = prompt_dir / "pi_diagnosis_prompt.md"
    return path.read_text(encoding="utf-8")


def build_pi_prompt(
    *, evidence_file: Path, original_filename: str, redaction_count: int, max_turns: int,
    user_message: str = "",
) -> str:
    """Build the StorageOps prompt sent to Pi. No mode switching — one unified prompt."""
    prompt = _load_prompt()
    replacements = {
        "{{ evidence_file }}": str(evidence_file),
        "{{ original_filename }}": original_filename,
        "{{ redaction_count }}": str(redaction_count),
        "{{ max_turns }}": str(max_turns),
        "{{ user_message }}": user_message,
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


def _event_is_final(event: dict[str, Any]) -> bool:
    """Return True when Pi signals the agent turn is complete."""
    typ = str(event.get("type") or event.get("event") or "").lower()
    return typ == "agent_end"


def reconstruct_report_from_events(events: list[dict[str, Any]]) -> str:
    """Extract final assistant response from Pi RPC JSONL event stream."""
    # Primary: extract from agent_end.messages (most reliable)
    raw = ""
    for event in reversed(events):
        if str(event.get("type") or "").lower() == "agent_end":
            for msg in reversed(event.get("messages", [])):
                if msg.get("role") == "assistant":
                    texts = [
                        block["text"]
                        for block in msg.get("content", [])
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    if texts:
                        raw = "\n".join(texts)
                        break
            if raw:
                break

    # Fallback: reassemble from streaming text_delta events
    if not raw:
        chunks: list[str] = []
        for event in events:
            if str(event.get("type") or "").lower() == "message_update":
                ae = event.get("assistantMessageEvent", {})
                if isinstance(ae, dict) and ae.get("type") == "text_delta":
                    delta = ae.get("delta", "")
                    if delta:
                        chunks.append(delta)
        raw = "".join(chunks)

    return raw


class PiSession:
    """
    A long-lived Pi process for a REPL session.

    Maintains one Pi subprocess across multiple turns, sending messages via JSONL RPC.
    This preserves conversation history — each turn's prompt includes prior messages so
    the model remembers earlier interactions.
    """

    runtime_name = "pi"

    def __init__(self, options: AgentRunOptions):
        self.options = options
        self.proc: subprocess.Popen | None = None
        self._events: list[dict[str, Any]] = []
        self._session_id: str = ""
        self._conversation_turns: list[str] = []  # user messages for history

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def raw_events(self) -> list[dict[str, Any]]:
        return self._events

    def start(self) -> AgentRunResult | None:
        """Launch the Pi subprocess. Returns error result on failure, None on success."""
        try:
            self._session_id = str(__import__("uuid").uuid4())[:8]
            self.proc = subprocess.Popen(
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
            return None
        except FileNotFoundError:
            return AgentRunResult(False, self.runtime_name, error=_PI_NOT_FOUND_MSG)
        except OSError as exc:
            return AgentRunResult(False, self.runtime_name, error=f"Failed to start Pi: {exc}")

    def send(
        self,
        prompt: str,
        evidence_path: Path | None = None,
        event_callback: Any = None,
        stream: bool = False,
    ) -> AgentRunResult:
        """Send a prompt to the Pi process and collect the response.

        For the first turn of a session, sends the full StorageOps system prompt.
        For subsequent turns, sends just the user message with conversation context.
        Returns AgentRunResult with the assistant response in report_markdown.
        """
        if self.proc is None or self.proc.poll() is not None:
            # Process died or never started — attempt restart
            err = self.start()
            if err is not None:
                return err
            assert self.proc is not None

        assert self.proc.stdin is not None
        assert self.proc.stdout is not None

        deadline = time.monotonic() + self.options.timeout_seconds
        events: list[dict[str, Any]] = []
        saw_final = False

        try:
            self.proc.stdin.write(json.dumps(
                {"type": "prompt", "message": prompt}, ensure_ascii=False
            ) + "\n")
            self.proc.stdin.flush()

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.proc.kill()
                    self.proc = None
                    return AgentRunResult(
                        False,
                        self.runtime_name,
                        raw_events=events,
                        error=f"Pi RPC timed out after {self.options.timeout_seconds} seconds",
                    )
                ready, _, _ = select.select([self.proc.stdout], [], [], min(0.1, remaining))
                if not ready:
                    if self.proc.poll() is not None:
                        break
                    continue
                line = self.proc.stdout.readline()
                if not line:
                    if self.proc.poll() is not None:
                        break
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "raw_line", "text": line.strip()}
                safe = _safe_event(event)
                events.append(safe)
                self._events.append(safe)
                if event_callback:
                    try:
                        event_callback(safe)
                    except Exception:
                        pass
                elif stream:
                    # No callback: stream text_delta to stdout directly
                    typ = str(safe.get("type") or "").lower()
                    if typ == "message_update":
                        ae = safe.get("assistantMessageEvent", {})
                        if isinstance(ae, dict) and ae.get("type") == "text_delta":
                            delta = ae.get("delta", "")
                            if delta:
                                print(delta, end="", flush=True)
                if _event_is_final(event):
                    saw_final = True
                    break

            if not saw_final:
                # Drain remaining stdout
                try:
                    remaining_out = self.proc.stdout.read() if self.proc.stdout else ""
                    for line in remaining_out.splitlines():
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            event = {"type": "raw_line", "text": line.strip()}
                        safe = _safe_event(event)
                        events.append(safe)
                        self._events.append(safe)
                        if _event_is_final(event):
                            saw_final = True
                except OSError:
                    pass

                stderr_raw = ""
                try:
                    self.proc.wait(timeout=2)
                    stderr_raw = self.proc.stderr.read() if self.proc.stderr else ""
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait()
                except OSError:
                    pass

                if self.proc.returncode not in (0, None) and not saw_final:
                    err = redact_for_pi(stderr_raw or "Pi RPC failed")[0]
                    self.proc = None
                    return AgentRunResult(False, self.runtime_name, raw_events=events, error=err)

                # Pi process finished the turn but stdin is closed — restart for next turn
                self.proc.stdin.close() if self.proc.stdin else None
                self.proc.wait()
                self.proc = None
                # Auto-restart Pi on next send()
                err = self.start()
                if err is not None:
                    return AgentRunResult(
                        False, self.runtime_name, raw_events=events, error=err.error or "Failed to restart Pi"
                    )

            report = reconstruct_report_from_events(events)

            # Safety lint: scan for secrets and dangerous recommendations
            if report:
                lint = safety_lint(report)
                if lint["issues"]:
                    # Append safety notes as a gentle reminder instead of blocking
                    report += "\n\n---\n\n⚠️  Safety note: " + "; ".join(lint["issues"])

                # Auto-save to memory on success (best-effort)
                try:
                    from storageops.memory_store import save_case
                    save_case(
                        self._session_id,
                        "diagnosis",
                        "general",
                        report[:400],
                        keywords=[],
                    )
                except Exception:
                    pass

            return AgentRunResult(
                True,
                self.runtime_name,
                report_markdown=report,
                raw_events=events,
            )

        except Exception as exc:
            return AgentRunResult(False, self.runtime_name, raw_events=events, error=str(exc))

    def stop(self) -> None:
        """Cleanly terminate the Pi subprocess."""
        if self.proc and self.proc.poll() is None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None

    # Default models per provider when no explicit --model is set.
    _DEFAULT_MODELS: dict[str, str] = {
        "deepseek": "deepseek/deepseek-v4-flash:off",
        "openai": "openai/gpt-4o-mini",
        "anthropic": "anthropic/claude-sonnet-4-20250514",
        "google": "google/gemini-3-flash-preview",
    }

    def _command(self) -> list[str]:
        cmd = [self.options.pi_command, "--mode", "rpc"]
        provider = self.options.pi_provider or _cfg_provider() or ""
        if provider:
            cmd.extend(["--provider", provider])
        api_key = _cfg_api_key()
        if api_key:
            cmd.extend(["--api-key", api_key])
        model = self.options.pi_model or self._DEFAULT_MODELS.get(provider, "")
        if model:
            cmd.extend(["--model", model])
        return cmd

    def _pi_env(self) -> dict:
        env = os.environ.copy()
        api_key = _cfg_api_key()
        if api_key:
            provider = self.options.pi_provider or _cfg_provider() or ""
            env_map = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai":    "OPENAI_API_KEY",
            }
            env_var = env_map.get(provider, f"{provider.upper()}_API_KEY")
            env.setdefault(env_var, api_key)
        return env


# ── Legacy PiRpcRuntime (one-shot, stateless — kept for CLI commands) ──

class PiRpcRuntime:
    """One-shot Pi RPC runner for standalone commands (triage, analyze, eval)."""

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
                user_message=redacted_text[:500],
            )
            prompt = redact_for_pi(prompt)[0]

            session = PiSession(self.options)
            start_err = session.start()
            if start_err:
                return start_err

            result = session.send(
                prompt,
                evidence_path=evidence_path,
                event_callback=self.options.event_callback,
                stream=self.options.stream,
            )
            session.stop()

            log_pi_result(
                session_id,
                ok=result.ok,
                redaction_count=redaction_count,
                validation_ok=result.ok,
                event_count=len(result.raw_events),
            )
            log_session_end(session_id, "success" if result.ok else "failed")
            return result


__all__ = [
    "PiSession",
    "PiRpcRuntime",
    "redact_for_pi",
    "build_pi_prompt",
    "reconstruct_report_from_events",
    "_MIGRATION_ERROR",
]
