"""
Pi Coding Agent RPC runtime — subprocess manager and event streamer.

Protocol:
  → stdin:  {"type": "prompt",      "message": "..."}
  → stdin:  {"type": "tool_result",  "id": "...", "result": {...}}
  ← stdout: {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "..."}}
  ← stdout: {"type": "tool_execution_start", "executionId": "...", "toolName": "...", "input": {...}}
  ← stdout: {"type": "agent_end", ...}
"""
from __future__ import annotations

import fcntl
import json
import os
import select
import subprocess
import time
from typing import Any, Generator

_DEFAULT_MODELS: dict[str, str] = {
    "deepseek": "deepseek/deepseek-v4-flash:off",
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-sonnet-4-20250514",
    "google": "google/gemini-3-flash-preview",
}


def _default_model(provider: str) -> str:
    return _DEFAULT_MODELS.get(provider, "")


class PiRuntime:
    """Manage a Pi subprocess in RPC mode. One instance = one Pi process."""

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

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self) -> dict | None:
        """Launch Pi subprocess. Returns error dict on failure, None on success."""
        if self._proc is not None and self._proc.poll() is None:
            return None  # already running

        env = os.environ.copy()
        if self.api_key:
            env["DEEPSEEK_API_KEY"] = self.api_key
            env["ANTHROPIC_API_KEY"] = self.api_key
            env["OPENAI_API_KEY"] = self.api_key

        cmd = [self.pi_command, "--rpc"]
        if self.pi_model:
            cmd.extend(["--model", self.pi_model])

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            return {"error": f"Pi not found at {self.pi_command}. Run: storageops setup"}
        except Exception as exc:
            return {"error": f"Failed to start Pi: {exc}"}

        # Set stdout to non-blocking
        fd = self._proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        self._started = True
        return None

    def stop(self) -> None:
        """Terminate the Pi subprocess."""
        self._started = False
        if self._proc:
            try:
                self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    # ── Streaming ────────────────────────────────────────────

    def stream(self, prompt: str) -> Generator[dict[str, Any], None, None]:
        """Send a prompt and yield normalized events until agent_end.

        Yields:
          {"type": "text_delta", "delta": "..."}
          {"type": "think_block", "text": "..."}
          {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
          {"type": "tool_result", "id": "...", "name": "...", "ok": bool, "summary": "..."}
          {"type": "agent_end", "messages": [...]}
          {"type": "error", "message": "..."}
        """
        err = self.start()
        if err:
            yield {"type": "error", "message": err.get("error", "Pi failed")}
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
        payload = {"type": "tool_result", "id": tool_id, "result": result}
        try:
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._proc.stdin.flush()
        except OSError:
            pass

    # ── Event normalization ──────────────────────────────────

    @staticmethod
    def _normalize_event(raw: dict) -> dict | None:
        """Convert Pi RPC events to simplified normalized form."""
        typ = str(raw.get("type") or "").lower()

        # --- Text deltas (message_update) ---
        if typ == "message_update":
            ae = raw.get("assistantMessageEvent", {})
            if isinstance(ae, dict):
                ae_type = ae.get("type", "")
                if ae_type == "text_delta":
                    return {"type": "text_delta", "delta": ae.get("delta", "")}
                if ae_type == "text_start":
                    return {"type": "text_delta", "delta": ae.get("text", ae.get("delta", ""))}
            return None

        # --- Thinking ---
        if typ in ("thinking_delta", "thinking"):
            return {
                "type": "think_block",
                "text": raw.get("thinking", raw.get("text", "")),
                "signature": raw.get("thinkingSignature", ""),
            }

        # --- Tool call ---
        if typ == "tool_execution_start":
            return {
                "type": "tool_call",
                "id": raw.get("executionId", raw.get("id", "")),
                "name": raw.get("toolName", raw.get("name", "")),
                "arguments": raw.get("input", raw.get("arguments", {})),
            }

        # --- Tool result ---
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

        # --- Terminal events ---
        if typ in ("agent_end",):
            return {"type": "agent_end", "messages": raw.get("messages", [])}

        # --- Events we skip ---
        if typ in (
            "turn_start", "turn_end", "message_start", "message_end",
            "response", "agent_start", "session",
        ):
            return None

        # Unknown — pass through
        return None
