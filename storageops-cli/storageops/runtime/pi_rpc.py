"""Pi Coding Agent JSONL RPC runtime — simplified process manager.

Owns the Pi subprocess lifecycle and streams RPC events. All session
management, prompt building, and safety logic now lives in core/agent.py.

Protocol:
  → stdin:  {"type": "prompt",    "message": "..."}
  → stdin:  {"type": "tool_result", "id": "...", "result": {...}}
  ← stdout: {"type": "text_delta", "delta": "..."}
  ← stdout: {"type": "tool_call",  "name": "...", "arguments": {...}}
  ← stdout: {"type": "agent_end", ...}
"""
from __future__ import annotations

import fcntl
import json
import os
import os as _os_mod
import select
import subprocess
import time
from pathlib import Path
from typing import Any, Generator

from storageops.runtime.base import AgentRunOptions, AgentRunResult


_PI_NOT_FOUND = """\
Pi Agent not found on PATH. Run: storageops setup"""

_DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek/deepseek-v4-flash:off",
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-sonnet-4-20250514",
    "google": "google/gemini-3-flash-preview",
}


def _default_model(provider: str) -> str:
    return _DEFAULT_MODELS.get(provider, "")


def _pi_workdir() -> Path:
    from storageops.config import get_workdir as _cfg_workdir
    d = _cfg_workdir()
    d.mkdir(parents=True, exist_ok=True)
    return d


class PiRuntime:
    """Manages a single Pi RPC subprocess.

    Created per Agent instance. Handles start/stop and event streaming.
    """

    def __init__(
        self,
        max_turns: int = 10,
        timeout_seconds: int = 600,
        pi_command: str | None = None,
        pi_model: str | None = None,
        pi_provider: str | None = None,
    ) -> None:
        from storageops.config import get_pi_command, get_api_key, get_provider

        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.pi_command = pi_command or get_pi_command()
        self.pi_model = pi_model or _default_model(get_provider() or "deepseek")
        self.pi_provider = pi_provider or get_provider() or ""
        self.api_key = get_api_key() or ""

        self._proc: subprocess.Popen | None = None
        self._started: bool = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> AgentRunResult | None:
        """Launch the Pi subprocess. Returns error on failure."""
        if self._proc and self._proc.poll() is None:
            return None  # Already running

        cmd = [self.pi_command, "--mode", "rpc"]
        if self.pi_provider:
            cmd.extend(["--provider", self.pi_provider])
        if self.api_key:
            cmd.extend(["--api-key", self.api_key])
        if self.pi_model:
            cmd.extend(["--model", self.pi_model])

        env = os.environ.copy()
        if self.api_key and self.pi_provider:
            env_var = f"{self.pi_provider.upper()}_API_KEY"
            env.setdefault(env_var, self.api_key)

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(_pi_workdir()),
                env=env,
            )
            # Set stdout to non-blocking for reliable event reading
            fd = self._proc.stdout.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | _os_mod.O_NONBLOCK)
            self._started = True
            return None
        except FileNotFoundError:
            return AgentRunResult(False, "pi", error=_PI_NOT_FOUND)
        except OSError as exc:
            return AgentRunResult(False, "pi", error=f"Failed to start Pi: {exc}")

    def stop(self) -> None:
        """Terminate the Pi subprocess."""
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
            except OSError:
                pass
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
            self._proc = None
            self._started = False

    def _ensure_started(self) -> AgentRunResult | None:
        if not self._started or (self._proc and self._proc.poll() is not None):
            return self.start()
        return None

    # ── Streaming ──────────────────────────────────────────────────────

    def stream(self, prompt: str) -> Generator[dict[str, Any], None, None]:
        """Send a prompt and yield parsed events until agent_end.

        Yields dicts like:
          {"type": "text_delta", "delta": "..."}
          {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
          {"type": "agent_end", "messages": [...]}
        """
        err = self._ensure_started()
        if err:
            yield {"type": "error", "message": err.error or "Pi failed to start"}
            return

        assert self._proc and self._proc.stdin and self._proc.stdout

        # Write prompt
        self._proc.stdin.write(
            json.dumps({"type": "prompt", "message": prompt}, ensure_ascii=False) + "\n"
        )
        self._proc.stdin.flush()

        deadline = time.monotonic() + self.timeout_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                yield {"type": "error", "message": f"Pi timed out after {self.timeout_seconds}s"}
                self.stop()
                return

            # Read all available lines (non-blocking)
            had_data = False
            while True:
                try:
                    line = self._proc.stdout.readline()
                    if not line:
                        break
                    had_data = True
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Normalize events for the Agent
                    evt = self._normalize_event(event)
                    if evt:
                        yield evt
                        if evt.get("type") == "agent_end":
                            return
                except (IOError, OSError):
                    break

            if self._proc.poll() is not None:
                break

            # Wait for more data
            ready, _, _ = select.select(
                [self._proc.stdout], [], [], min(0.5, remaining)
            )
            if not ready and self._proc.poll() is not None:
                break

        yield {"type": "error", "message": "Pi process exited unexpectedly"}
        self.stop()

    def send_tool_result(self, tool_id: str, result: Any) -> None:
        """Send a tool execution result back to Pi."""
        if not self._proc or not self._proc.stdin:
            return

        # Convert ToolResult to Pi-compatible format
        if hasattr(result, "ok"):
            payload = {
                "type": "tool_result",
                "id": tool_id,
                "ok": result.ok,
                "result": {
                    "ok": result.ok,
                    "summary": getattr(result, "summary", ""),
                    "error": getattr(result, "error", ""),
                    "elapsed": getattr(result, "elapsed", 0),
                },
            }
        else:
            payload = {"type": "tool_result", "id": tool_id, "result": result}

        try:
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
        except OSError:
            pass

    # ── Event normalization ────────────────────────────────────────────

    @staticmethod
    def _normalize_event(raw: dict) -> dict | None:
        """Convert Pi RPC event to a normalized form the Agent understands."""
        typ = str(raw.get("type") or "").lower()

        if typ == "message_update":
            ae = raw.get("assistantMessageEvent", {})
            if isinstance(ae, dict):
                ae_type = ae.get("type", "")
                if ae_type == "text_delta":
                    return {"type": "text_delta", "delta": ae.get("delta", "")}
                if ae_type == "text_start":
                    return {"type": "text_delta", "delta": ae.get("text", ae.get("delta", ""))}
            return None

        if typ == "tool_execution_start":
            return {
                "type": "tool_call",
                "id": raw.get("executionId", raw.get("id", "")),
                "name": raw.get("toolName", raw.get("name", "")),
                "arguments": raw.get("input", raw.get("arguments", {})),
            }

        if typ == "tool_execution_end":
            is_error = bool(raw.get("isError"))
            result = raw.get("result", {})
            content = ""
            if isinstance(result, dict):
                cl = result.get("content", [])
                if isinstance(cl, list) and cl and isinstance(cl[0], dict):
                    text = cl[0].get("text", "")
                    if isinstance(text, str):
                        try:
                            data = json.loads(text)
                            # Build summary from structured result
                            parts = []
                            for k in ("records", "findings", "count"):
                                v = data.get(k)
                                if isinstance(v, list):
                                    parts.append(f"{len(v)} {k}")
                                elif isinstance(v, int):
                                    parts.append(f"{v} {k}")
                            content = "  ".join(parts[:3])
                        except json.JSONDecodeError:
                            content = text[:100]
            return {
                "type": "tool_result",
                "id": raw.get("executionId", ""),
                "name": raw.get("toolName", ""),
                "ok": not is_error,
                "summary": content,
                "error": raw.get("error", "") if is_error else "",
            }

        if typ in ("agent_end",):
            return {"type": "agent_end", "messages": raw.get("messages", [])}

        if typ == "turn_end":
            return None  # Don't stop streaming; agent_end signals completion

        if typ in ("thinking_delta", "thinking"):
            return {"type": "think_block", "text": raw.get("thinking", raw.get("text", "")),
                    "signature": raw.get("thinkingSignature", "")}

        if typ == "turn_start":
            return None  # Stream display handles this; Agent doesn't need it

        if typ == "message_start":
            return None

        if typ == "message_end":
            return None

        if typ == "response":
            return None

        if typ == "agent_start":
            return None

        # Unknown — pass through
        return {"type": typ, "raw": raw}
