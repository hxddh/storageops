"""Streaming display for the REPL — renders agent events in real-time.

Three display zones (top to bottom):
  1. Thinking (dim, folded when verbose=False — only first line shown)
  2. Tool calls (tool name + result summary + elapsed)
  3. Response text (streamed character-by-character)

All rendering is TTY-aware; non-TTY falls back to plain output.
"""
from __future__ import annotations

import json
import time
from typing import Any

from storageops.ui.terminal import c, dim, green, red, cyan, is_tty


class StreamDisplay:
    """Live event renderer for the interactive REPL."""

    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose
        self._thinking_lines: list[str] = []
        self._thinking_visible: bool = False
        self._current_tool: str | None = None
        self._t_start: float | None = None
        self._response_started: bool = False
        self._tool_count: int = 0

    # ── Public API ─────────────────────────────────────────────────

    def on_event(self, event: dict[str, Any]) -> None:
        """Handle a single agent event (dict from Agent/Pi)."""
        if not is_tty():
            return

        typ = event.get("type", "")

        if typ == "text_delta":
            self._show_text(event.get("delta", ""))
        elif typ == "tool_call":
            self._show_tool_start(event.get("name", ""))
        elif typ == "tool_result":
            self._show_tool_end(event)
        elif typ == "think_block":
            self._show_thinking(event.get("text", ""))
        elif typ == "agent_end":
            self._finish()

    def on_raw(self, event: dict[str, Any]) -> None:
        """Handle raw Pi RPC events (before Agent normalization)."""
        if not is_tty():
            return

        typ = str(event.get("type") or "").lower()

        # Handle Pi's raw event format directly
        if typ == "message_update":
            ae = event.get("assistantMessageEvent", {})
            if isinstance(ae, dict) and ae.get("type") == "text_delta":
                self._show_text(ae.get("delta", ""))
            return

        if typ == "tool_execution_start":
            self._show_tool_start(event.get("toolName", ""))
            return

        if typ == "tool_execution_end":
            self._show_tool_end(event)
            return

        if typ in ("agent_end", "turn_end"):
            self._finish()
            return

        if typ == "turn_start":
            self._t_start = time.monotonic()
            return

        # Forward to standard handler
        self.on_event(event)

    # ── Internal rendering ─────────────────────────────────────────

    def _show_thinking(self, text: str) -> None:
        if not text.strip():
            return

        if not self._thinking_visible:
            self._thinking_visible = True
            if self._response_started:
                print()
            print(dim("  ── Thinking ──"))
            self._t_start = self._t_start or time.monotonic()

        if self._verbose:
            # Show full thinking text
            for line in text.split("\n"):
                print(dim(f"  {line}"))
            self._thinking_lines = []
        else:
            # Buffer up to 3 lines; show first + count remainder
            self._thinking_lines.extend(text.split("\n"))
            if len(self._thinking_lines) == 1:
                print(dim(f"  {self._thinking_lines[0][:120]}"))
            # For subsequent, just update the last shown line count

    def _show_tool_start(self, name: str) -> None:
        if not name:
            return
        self._current_tool = name
        self._tool_count += 1
        self._t_start = self._t_start or time.monotonic()
        print(f"  {c('⏺', 'cyan')}  {c(name, 'cyan')}", end="", flush=True)

    def _show_tool_end(self, event: dict) -> None:
        if not self._current_tool:
            return

        is_error = bool(event.get("isError") or not event.get("ok", True))
        summary = event.get("summary", "")
        elapsed = ""
        if self._t_start:
            elapsed = f"{(time.monotonic() - self._t_start):.1f}s"

        mark = red("✗") if is_error else green("✓")
        detail = summary or ("error" if is_error else "ok")
        elapsed_str = dim(f" ({elapsed})") if elapsed else ""

        print(f"  {mark} {dim(detail)}{elapsed_str}")
        self._current_tool = None

    def _show_text(self, delta: str) -> None:
        if not delta:
            return
        if not self._response_started:
            self._response_started = True
            if self._thinking_visible:
                print()  # Separator between thinking and response
        print(delta, end="", flush=True)

    def _finish(self) -> None:
        if self._thinking_visible and not self._response_started:
            print()
        self._response_started = False
        self._thinking_visible = False
        self._thinking_lines.clear()
        self._t_start = None

    def reset(self) -> None:
        self._thinking_lines.clear()
        self._thinking_visible = False
        self._current_tool = None
        self._t_start = None
        self._response_started = False
        self._tool_count = 0
