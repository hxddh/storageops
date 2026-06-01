"""
Thin Pi subprocess manager.

Starts Pi in rpc mode (--rpc), communicates via stdin/stdout JSON lines.
Uses config.py for provider/model/api_key settings.
"""
from __future__ import annotations

import json
import os
import fcntl
import subprocess
import threading
import time

# Default model per provider when none specified
_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "anthropic/claude-sonnet-4",
    "openai": "openai/gpt-4o",
}


class PiRuntime:
    """Manage a Pi subprocess in RPC mode.

    Usage:
        pi = PiRuntime()
        pi.send_prompt("Hello")
        while True:
            event = pi.read_event()
            if event is None: break
            # process event
    """

    def __init__(self, provider: str = "", model: str = "", api_key: str = "") -> None:
        from storageops.config import get_pi_command, get_provider, get_api_key

        self._provider = provider or get_provider()
        self._model = model or ""
        api_key = api_key or get_api_key()

        # Resolve Pi binary path
        pi_cmd = get_pi_command()

        # Build env with API key
        env = os.environ.copy()
        if api_key:
            provider_upper = self._provider.upper()
            env[f"{provider_upper}_API_KEY"] = api_key

        cmd = [pi_cmd, "--rpc"]
        if self._model:
            # Ensure model string has provider prefix if it's just a model name
            resolved = self._model
            if "/" not in resolved and self._provider:
                resolved = f"{self._provider}/{resolved}"
            elif "/" not in resolved:
                resolved = _DEFAULT_MODELS.get(self._provider, self._model)
            cmd.extend(["--model", resolved])

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )

        # Make stdout non-blocking
        fd = self._proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        self._lock = threading.Lock()
        self._last_ack = time.monotonic()
        self._ack_thread: threading.Thread | None = None
        self._running = True

        # Start ack heartbeat
        self._ack_thread = threading.Thread(target=self._ack_loop, daemon=True)
        self._ack_thread.start()

    def send_prompt(self, text: str) -> None:
        """Write a prompt to Pi's stdin."""
        # Auto-wrap with YAML header if missing
        if not text.lstrip().startswith("---"):
            provider_line = self._provider
            model_line = self._model
            text = f"---\nprovider: {provider_line}\nmodel: {model_line}\n---\n\n{text}"

        msg = json.dumps({"prompt": text}, ensure_ascii=False) + "\n"
        with self._lock:
            self._proc.stdin.write(msg)
            self._proc.stdin.flush()

    def send_tool_result(self, call_id: str, result: dict) -> None:
        """Send a tool result back to Pi."""
        msg = json.dumps({"call_id": call_id, "tool_result": result}, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            self._proc.stdin.write(msg)
            self._proc.stdin.flush()

    def read_event(self) -> dict | None:
        """Read one JSON event from Pi's stdout. Returns None if no data available."""
        try:
            line = self._proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                return None
            return json.loads(line)
        except (IOError, BlockingIOError):
            return None
        except json.JSONDecodeError:
            return None

    def acknowledge(self) -> None:
        """Send an ack to prevent timeout."""
        self._last_ack = time.monotonic()

    def stop(self) -> None:
        """Terminate the Pi subprocess gracefully."""
        self._running = False
        try:
            self._proc.stdin.close()
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()

    def _ack_loop(self) -> None:
        """Periodic ack heartbeat thread."""
        while self._running:
            time.sleep(10)
            if time.monotonic() - self._last_ack > 15:
                try:
                    with self._lock:
                        self._proc.stdin.write('{"ack":true}\n')
                        self._proc.stdin.flush()
                    self._last_ack = time.monotonic()
                except Exception:
                    break
