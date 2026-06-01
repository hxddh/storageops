"""
Stateless agent loop: converse() streams Pi events through a display.

Uses Pi RPC protocol via PiRuntime.stream(). The agent is a pure function
that takes a session + user input + display, and drives the ReAct loop:
  prompt → Pi → events → tool calls → Pi → ... → response
"""
from __future__ import annotations

import time
from typing import Protocol

from storageops.session import Session
from storageops.context import build_prompt
from storageops.tool_registry import dispatch_tool


# ── Display protocol ─────────────────────────────────────────

class Display(Protocol):
    def show_thinking(self, text: str) -> None: ...
    def show_text_delta(self, text: str) -> None: ...
    def show_tool_call(self, name: str, args: dict) -> None: ...
    def show_tool_result(self, name: str, summary: str) -> None: ...
    def show_result(self, elapsed_ms: float) -> None: ...
    def show_error(self, msg: str) -> None: ...


class PiRunResult:
    def __init__(self) -> None:
        self.text: str = ""
        self.events: list[dict] = []
        self.tool_calls: list[dict] = []
        self.errors: list[str] = []
        self.elapsed_ms: float = 0


# ── Main conversation loop ───────────────────────────────────

def converse(session: Session, user_input: str, display: Display) -> None:
    """Run one conversation turn with Pi.

    Writes user_turn to session, streams Pi events, dispatches tools,
    updates session metadata. Side effects: session writes, display output.
    """
    from storageops.pi_runtime import PiRuntime

    t0 = time.monotonic()

    # Record user turn
    session.append({"type": "user_turn", "prompt": user_input, "ts": _now_iso()})

    # Build prompt with conversation history
    prompt = build_prompt(session, user_input)

    # Start Pi and stream events
    pi = PiRuntime()
    accumulated = ""

    for event in pi.stream(prompt):
        event_type = event.get("type", "")

        # Persist every event to session (for replay / resume)
        session.append(event)

        if event_type == "think_block":
            text = event.get("text", "")
            if text:
                display.show_thinking(text)

        elif event_type == "text_delta":
            delta = event.get("delta", "")
            accumulated += delta
            display.show_text_delta(delta)

        elif event_type == "tool_call":
            name = event.get("name", "unknown")
            args = event.get("arguments", {})
            call_id = event.get("id", "")
            display.show_tool_call(name, args)

            try:
                result = dispatch_tool(name, args)
                summary = _summarize_result(name, result)
                display.show_tool_result(name, summary)
                pi.send_tool_result(call_id, result)
            except Exception as exc:
                err = {"error": str(exc)}
                display.show_error(f"Tool {name} error: {exc}")
                pi.send_tool_result(call_id, err)

        elif event_type == "tool_result":
            # tool_result events from Pi are informational
            pass

        elif event_type == "error":
            display.show_error(event.get("message", "Unknown error"))

        elif event_type == "agent_end":
            break

    pi.stop()

    elapsed = (time.monotonic() - t0) * 1000
    display.show_result(elapsed)

    # Sync session metadata
    session.sync_meta()


def converse_one_shot(prompt: str) -> PiRunResult:
    """Run Pi once for a complete response. No session, no display.

    Used by API server and CLI for single-turn diagnostic runs.
    """
    from storageops.pi_runtime import PiRuntime

    result = PiRunResult()
    t0 = time.monotonic()

    pi = PiRuntime()

    for event in pi.stream(prompt):
        result.events.append(event)
        event_type = event.get("type", "")

        if event_type == "text_delta":
            delta = event.get("delta", "")
            result.text += delta

        elif event_type == "tool_call":
            name = event.get("name", "unknown")
            args = event.get("arguments", {})
            call_id = event.get("id", "")
            result.tool_calls.append({"name": name, "args": args})

            try:
                tool_result = dispatch_tool(name, args)
                pi.send_tool_result(call_id, tool_result)
            except Exception as exc:
                err_msg = f"Tool {name}: {exc}"
                result.errors.append(err_msg)
                pi.send_tool_result(call_id, {"error": str(exc)})

        elif event_type == "error":
            result.errors.append(event.get("message", "Unknown error"))

        elif event_type == "agent_end":
            break

    pi.stop()

    result.elapsed_ms = (time.monotonic() - t0) * 1000
    return result


# ── Helpers ──────────────────────────────────────────────────

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _summarize_result(name: str, result: dict) -> str:
    """Short summary of a tool result for display."""
    if not isinstance(result, dict):
        return str(result)[:200]
    if error := result.get("error"):
        return f"error: {str(error)[:150]}"
    for key in ("ok", "count", "status", "root_cause", "domain"):
        if key in result:
            return f"{key}={result[key]}"
    if "summary" in result:
        return str(result["summary"])[:150]
    if "findings" in result:
        cnt = result["findings"] if isinstance(result["findings"], int) else len(result["findings"])
        return f"findings={cnt}"
    keys = list(result.keys())[:5]
    return f"keys: {', '.join(keys)}"
