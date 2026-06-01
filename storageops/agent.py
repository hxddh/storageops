"""
Stateless agent loop: converse() streams Pi events through a display.

Pure functions — no global state, no side effects beyond session writes
and display output. Designed for REPL, CLI, and API usage.
"""
from __future__ import annotations

import time
import json
from typing import Protocol

from storageops.session import Session
from storageops.context import build_prompt
from storageops.tool_registry import dispatch_tool


# ── Display protocol ──────────────────────────────────────────────────

class Display(Protocol):
    """Protocol for streaming output renders."""
    def show_thinking(self, text: str) -> None: ...
    def show_text_delta(self, text: str) -> None: ...
    def show_tool_call(self, name: str, args: dict) -> None: ...
    def show_tool_result(self, name: str, summary: str) -> None: ...
    def show_result(self, elapsed_ms: float) -> None: ...
    def show_progress(self, total: int, current: int) -> None: ...
    def show_error(self, msg: str) -> None: ...


# ── PiRunResult ───────────────────────────────────────────────────────

class PiRunResult:
    """Result from a one-shot Pi run (converse_one_shot)."""
    def __init__(self) -> None:
        self.text: str = ""
        self.events: list[dict] = []
        self.tool_calls: list[dict] = []
        self.errors: list[str] = []
        self.elapsed_ms: float = 0


# ── Main conversation loop ────────────────────────────────────────────

def converse(session: Session, user_input: str, display: Display) -> None:
    """Run a streaming conversation turn with Pi.

    Writes a user_turn event to the session, builds the prompt,
    streams Pi events, dispatches tool calls, and updates session metadata.
    Returns nothing — all output goes through Display.
    """
    from storageops.pi_runtime import PiRuntime

    t0 = time.monotonic()

    # Record user turn
    session.append({"type": "user_turn", "prompt": user_input, "ts": _now_iso()})

    # Build prompt
    prompt = build_prompt(session, user_input)

    # Start Pi
    pi = PiRuntime()
    pi.send_prompt(prompt)

    turn_count = 0
    max_turns = 20  # safety limit

    while turn_count < max_turns:
        turn_count += 1
        event = pi.read_event()
        if event is None:
            # No event ready, send ack and wait
            pi.acknowledge()
            time.sleep(0.05)
            continue

        event_type = event.get("type", "unknown")
        session.append(event)

        if event_type == "thinking":
            display.show_thinking(event.get("text", ""))

        elif event_type == "text_delta":
            display.show_text_delta(event.get("text", ""))

        elif event_type == "tool_call":
            name = event.get("name", "unknown")
            args = event.get("arguments", {})
            call_id = event.get("call_id", "")
            display.show_tool_call(name, args)

            # Dispatch the tool
            try:
                result = dispatch_tool(name, args)
                summary = _summarize_result(name, result)
                display.show_tool_result(name, summary)
                pi.send_tool_result(call_id, result)
            except Exception as exc:
                err = {"error": str(exc)}
                display.show_error(f"Tool {name} error: {exc}")
                pi.send_tool_result(call_id, err)

        elif event_type == "error":
            display.show_error(event.get("message", "Unknown error"))

        elif event_type == "agent_end":
            break

        elif event_type == "turn_end":
            # Pi wants to continue — loop keeps going
            continue

    if turn_count >= max_turns:
        display.show_error("Reached maximum turn limit")

    elapsed = (time.monotonic() - t0) * 1000
    display.show_result(elapsed)

    # Sync session metadata
    session.sync_meta()


def converse_one_shot(prompt: str) -> PiRunResult:
    """Run Pi once without session or display. Returns structured result.

    Used by API server and CLI for quick diagnostic runs.
    """
    from storageops.pi_runtime import PiRuntime

    result = PiRunResult()
    t0 = time.monotonic()

    pi = PiRuntime()
    pi.send_prompt(prompt)

    turn_count = 0
    max_turns = 20

    while turn_count < max_turns:
        turn_count += 1
        event = pi.read_event()
        if event is None:
            pi.acknowledge()
            time.sleep(0.05)
            continue

        result.events.append(event)

        if event.get("type") == "text_delta":
            result.text += event.get("text", "")

        elif event.get("type") == "tool_call":
            name = event.get("name", "unknown")
            args = event.get("arguments", {})
            call_id = event.get("call_id", "")
            result.tool_calls.append({"name": name, "args": args})

            try:
                tool_result = dispatch_tool(name, args)
                pi.send_tool_result(call_id, tool_result)
            except Exception as exc:
                err = {"error": str(exc)}
                result.errors.append(f"Tool {name}: {exc}")
                pi.send_tool_result(call_id, err)

        elif event.get("type") == "error":
            result.errors.append(event.get("message", "Unknown error"))

        elif event.get("type") == "agent_end":
            break

    result.elapsed_ms = (time.monotonic() - t0) * 1000
    return result


# ── Helpers ───────────────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _summarize_result(name: str, result: dict) -> str:
    """Create a short summary of a tool result for display."""
    if not isinstance(result, dict):
        return str(result)[:200]
    if error := result.get("error"):
        return f"error: {str(error)[:150]}"
    # Common patterns
    for key in ("ok", "count", "status", "root_cause", "domain"):
        if key in result:
            return f"{key}={result[key]}"
    # Try to find a meaningful summary key
    if "summary" in result:
        return str(result["summary"])[:150]
    if "findings" in result:
        cnt = result["findings"] if isinstance(result["findings"], int) else len(result["findings"])
        return f"findings={cnt}"
    # Fallback: show keys present
    keys = list(result.keys())[:5]
    return f"keys: {', '.join(keys)}"
