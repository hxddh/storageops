"""
Pure functions for prompt construction.

All functions are stateless — they take inputs and return strings.
"""
from __future__ import annotations

import re
from pathlib import Path

_IDENTITY_PATH = Path(__file__).parent / "prompts" / "identity.md"


def load_identity() -> str:
    """Load the identity/system prompt from storageops/prompts/identity.md."""
    if _IDENTITY_PATH.exists():
        return _IDENTITY_PATH.read_text(encoding="utf-8")
    return "You are StorageOps, a diagnostic assistant for object storage."


def format_tools() -> str:
    """Format available tools as a prompt section."""
    from storageops.tool_registry import TOOL_DEFINITIONS

    lines = ["## Available Tools\n"]
    for t in TOOL_DEFINITIONS:
        name = t["name"]
        desc = t.get("description", "").strip().split("\n")[0]
        lines.append(f"- **{name}**: {desc}")
    return "\n".join(lines)


def replay_history(session) -> str:
    """Format session replay messages for prompt context."""
    from storageops.session import Session

    messages = session.replay() if session else []
    if not messages:
        return ""

    lines = ["## Conversation History\n"]
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        # Truncate very long messages
        if len(content) > 2000:
            content = content[:2000] + "... [truncated]"
        lines.append(f"**{role.capitalize()}**: {content}\n")
    return "\n".join(lines)


def build_prompt(session, user_input: str) -> str:
    """Combine identity, tools, history, and user_input into a full prompt."""
    parts = [
        load_identity(),
        format_tools(),
        replay_history(session),
        f"## Current Request\n\n{user_input}",
    ]
    # Filter out empty parts
    return "\n\n".join(p for p in parts if p.strip())


def estimate_tokens(text: str) -> int:
    """Rough token estimate: chars / 4."""
    return max(1, len(text) // 4)


def compact_history(messages: list[dict], max_tokens: int) -> list[dict]:
    """Drop oldest messages until total tokens fit within max_tokens.

    Returns a new list (does not mutate input).
    """
    if not messages:
        return []

    # Estimate total tokens
    total = sum(estimate_tokens(m.get("content", "")) for m in messages)
    if total <= max_tokens:
        return list(messages)

    # Drop from the front (oldest) until we fit
    result = list(messages)
    while result and total > max_tokens:
        dropped = result.pop(0)
        total -= estimate_tokens(dropped.get("content", ""))

    return result
