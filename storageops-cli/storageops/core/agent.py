"""StorageOps Agent — natural-conversation diagnostic agent.

The Agent owns the ReAct loop: it builds prompts, streams events from
the LLM runtime (Pi Coding Agent), executes tool calls, and persists
everything to the session.

Architecture:
  Agent.run(user_input)
    → build prompt (identity + history + input)
    → stream events from Pi
    → for each event:
      - text_delta → yield ResponseText (for UI streaming)
      - tool_call → execute tool, yield ToolResult, send back to Pi
      - turn_end → save session, yield final result

The Agent is UI-agnostic; events are yielded as typed dataclasses.
The UI layer (repl.py, api_server.py) renders them for the user.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, AsyncIterator

from storageops.core.context import build_prompt, load_identity_prompt
from storageops.core.event import (
    UserMessage, AssistantMessage, ThinkBlock, ToolCall, ToolResult,
    TurnStart, TurnEnd, SessionMeta,
)
from storageops.core.session import Session
from storageops.core.tools import ToolRegistry
from storageops.runtime.pi_rpc import PiRuntime


# ── Redaction helper ─────────────────────────────────────────────────

def _redact_text(text: str) -> tuple[str, int]:
    """Redact secrets from text. Returns (redacted_text, count)."""
    try:
        from secret_scanner import scan as scan_secrets
        result = scan_secrets(text)
        return result["redacted_text"], result.get("count", 0)
    except Exception:
        return text, 0


# ── Agent ────────────────────────────────────────────────────────────

class Agent:
    """StorageOps diagnostic agent.

    Usage:
        agent = Agent(session=Session())
        async for event in agent.run("你好"):
            ui.render(event)
    """

    def __init__(
        self,
        session: Session | None = None,
        tools: ToolRegistry | None = None,
        runtime: PiRuntime | None = None,
        max_turns: int = 10,
        timeout_seconds: int = 600,
    ) -> None:
        self.session = session or Session()
        self.tools = tools or ToolRegistry()
        self.runtime = runtime or PiRuntime(max_turns=max_turns,
                                             timeout_seconds=timeout_seconds)
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds

    def run(self, user_input: str) -> list["TurnEvent"]:
        """Run one turn: user input → LLM → tool execution → response.

        Returns a list of turn events (UserMessage, ToolCall, ToolResult,
        AssistantMessage, TurnEnd). The session is auto-saved on completion.

        If a callback is set via self.on_event, it will be called for each
        raw event from Pi (before normalization).
        """
        events: list[Any] = []
        on_event = getattr(self, "on_event", None)

        # 1. Record user message
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        um = UserMessage(text=user_input, timestamp=ts)
        self.session.append(um)
        events.append(um)

        # 2. Build prompt
        prompt = build_prompt(self.session, user_input, {})
        prompt, _ = _redact_text(prompt)

        # 3. Start Pi runtime and stream
        t_start = time.monotonic()
        accumulated_text = ""

        try:
            for evt in self.runtime.stream(prompt):
                # Forward raw event to callback (for UI streaming)
                if on_event:
                    try:
                        on_event(evt)
                    except Exception:
                        pass

                typ = evt.get("type", "")

                # ── Thinking ────────────────────────────────────
                if typ == "think_block":
                    tb = ThinkBlock(
                        text=evt.get("text", ""),
                        signature=evt.get("signature", ""),
                    )
                    self.session.append(tb)
                    events.append(tb)

                # ── Text streaming ──────────────────────────────
                elif typ in ("text_delta", "assistant_text"):
                    delta = evt.get("delta", evt.get("text", ""))
                    if delta:
                        accumulated_text += delta
                        # Don't store individual deltas in session
                        # (they'll be in the final AssistantMessage)

                # ── Tool call ───────────────────────────────────
                elif typ == "tool_call":
                    tc = ToolCall(
                        id=evt.get("id", ""),
                        name=evt.get("name", evt.get("toolName", "")),
                        arguments=evt.get("arguments", evt.get("input", {})),
                        timestamp=ts,
                    )
                    self.session.append(tc)
                    events.append(tc)

                    # Execute the tool
                    result = self.tools.execute(tc)
                    self.session.append(result)
                    events.append(result)

                    # Send result back to Pi
                    self.runtime.send_tool_result(tc.id, result)

                # ── Turn end ────────────────────────────────────
                elif typ == "turn_end" or typ == "agent_end":
                    pass  # Handled after loop

        except Exception as exc:
            # If Pi fails, still save what we have
            accumulated_text += f"\n\n[Agent error: {exc}]"

        # 4. Record assistant response
        elapsed = time.monotonic() - t_start
        if accumulated_text.strip():
            am = AssistantMessage(text=accumulated_text, timestamp=ts)
            self.session.append(am)
            events.append(am)

        te = TurnEnd(elapsed=elapsed)
        self.session.append(te)
        events.append(te)

        # 5. Save session
        try:
            self.session.save()
        except OSError:
            pass

        return events

    def reset(self) -> None:
        """Reset the runtime for a new session."""
        self.runtime.stop()

    def resume(self, session_id: str) -> bool:
        """Load a session and replay context into the LLM.

        Returns True if the session was found and loaded.
        """
        loaded = Session.load(session_id)
        if loaded is None:
            return False
        self.session = loaded
        return True


# ── Legacy compatibility type ─────────────────────────────────────────

# TurnEvent is a union of all event types returned by Agent.run()
TurnEvent = UserMessage | ThinkBlock | ToolCall | ToolResult | AssistantMessage | TurnEnd
