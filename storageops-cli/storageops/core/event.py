"""Type-safe event definitions for the StorageOps agent pipeline.

Every interaction (user input, LLM thinking, tool calls, tool results,
streaming text) is represented as a typed event. Events are serializable
to/from JSON dicts for JSONL session persistence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json


# ── Event hierarchy ──────────────────────────────────────────────────

@dataclass
class SessionMeta:
    """Session-level metadata (always the first line in a JSONL file)."""
    id: str
    name: str = ""
    cwd: str = ""
    created: str = ""
    domain: str = ""

    def to_json(self) -> dict:
        return {"type": "session_meta", "id": self.id, "name": self.name,
                "cwd": self.cwd, "created": self.created, "domain": self.domain}

    @classmethod
    def from_json(cls, d: dict) -> "SessionMeta":
        return cls(id=d["id"], name=d.get("name", ""), cwd=d.get("cwd", ""),
                   created=d.get("created", ""), domain=d.get("domain", ""))


@dataclass
class ModelChange:
    """Indicates a model/provider change (useful for replay)."""
    provider: str = ""
    model: str = ""

    def to_json(self) -> dict:
        return {"type": "model_change", "provider": self.provider, "model": self.model}

    @classmethod
    def from_json(cls, d: dict) -> "ModelChange":
        return cls(provider=d.get("provider", ""), model=d.get("model", ""))


@dataclass
class UserMessage:
    """A message from the user."""
    text: str
    timestamp: str = ""

    def to_json(self) -> dict:
        return {"type": "user_message", "text": self.text, "timestamp": self.timestamp}

    @classmethod
    def from_json(cls, d: dict) -> "UserMessage":
        return cls(text=d["text"], timestamp=d.get("timestamp", ""))


@dataclass
class ThinkBlock:
    """An LLM thinking/reasoning block (partial or complete)."""
    text: str
    signature: str = ""

    def to_json(self) -> dict:
        return {"type": "think_block", "text": self.text, "signature": self.signature}

    @classmethod
    def from_json(cls, d: dict) -> "ThinkBlock":
        return cls(text=d.get("text", ""), signature=d.get("signature", ""))


@dataclass
class ToolCall:
    """An LLM-initiated tool call."""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_json(self) -> dict:
        return {"type": "tool_call", "id": self.id, "name": self.name,
                "arguments": self.arguments, "timestamp": self.timestamp}

    @classmethod
    def from_json(cls, d: dict) -> "ToolCall":
        return cls(id=d["id"], name=d["name"],
                   arguments=d.get("arguments", {}), timestamp=d.get("timestamp", ""))


@dataclass
class ToolResult:
    """The result of executing a tool."""
    id: str          # matches ToolCall.id
    name: str
    ok: bool
    summary: str = ""
    error: str = ""
    elapsed: float = 0.0
    raw: dict[str, Any] | None = None

    def to_json(self) -> dict:
        return {"type": "tool_result", "id": self.id, "name": self.name,
                "ok": self.ok, "summary": self.summary, "error": self.error,
                "elapsed": self.elapsed}

    @classmethod
    def from_json(cls, d: dict) -> "ToolResult":
        return cls(id=d["id"], name=d["name"], ok=d.get("ok", True),
                   summary=d.get("summary", ""), error=d.get("error", ""),
                   elapsed=d.get("elapsed", 0.0))


@dataclass
class AssistantMessage:
    """An assistant text response (complete, after streaming finishes)."""
    text: str
    timestamp: str = ""
    token_usage: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"type": "assistant_message", "text": self.text,
                "timestamp": self.timestamp, "token_usage": self.token_usage}

    @classmethod
    def from_json(cls, d: dict) -> "AssistantMessage":
        return cls(text=d.get("text", ""), timestamp=d.get("timestamp", ""),
                   token_usage=d.get("token_usage", {}))


@dataclass
class TurnStart:
    """Marks the start of an agent turn."""
    timestamp: str = ""

    def to_json(self) -> dict:
        return {"type": "turn_start", "timestamp": self.timestamp}

    @classmethod
    def from_json(cls, d: dict) -> "TurnStart":
        return cls(timestamp=d.get("timestamp", ""))


@dataclass
class TurnEnd:
    """Marks the end of an agent turn."""
    elapsed: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"type": "turn_end", "elapsed": self.elapsed, "token_usage": self.token_usage}

    @classmethod
    def from_json(cls, d: dict) -> "TurnEnd":
        return cls(elapsed=d.get("elapsed", 0.0), token_usage=d.get("token_usage", {}))


# ── Union type ───────────────────────────────────────────────────────

# All concrete event types
Event = (
    SessionMeta | ModelChange | UserMessage | ThinkBlock | ToolCall | ToolResult |
    AssistantMessage | TurnStart | TurnEnd
)

# ── Deserialization dispatch ─────────────────────────────────────────

_EVENT_REGISTRY: dict[str, type] = {
    "session_meta": SessionMeta,
    "model_change": ModelChange,
    "user_message": UserMessage,
    "think_block": ThinkBlock,
    "tool_call": ToolCall,
    "tool_result": ToolResult,
    "assistant_message": AssistantMessage,
    "turn_start": TurnStart,
    "turn_end": TurnEnd,
}


def event_from_json(d: dict) -> Event | None:
    """Deserialize a JSON dict into the correct Event type."""
    typ = d.get("type", "")
    cls = _EVENT_REGISTRY.get(typ)
    if cls is None:
        return None
    return cls.from_json(d)


def event_to_json(evt: Event) -> dict:
    """Serialize any Event to a JSON-serializable dict."""
    return evt.to_json()
