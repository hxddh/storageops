"""
Audit logger for StorageOps LLM agent sessions.

Writes JSONL records to ~/.storageops/audit.jsonl.
Each record has: ts, session_id, event type, and safe metadata.

Security: Never log raw text, tool inputs/outputs, or LLM messages.
Only log structural metadata (tool names, token counts, outcomes).
Secrets should already be redacted before they reach this layer.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


_AUDIT_DIR = Path.home() / ".storageops"
_AUDIT_FILE = _AUDIT_DIR / "audit.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(record: dict) -> None:
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def log_session_start(session_id: str, domain: str, provider: str) -> None:
    _write({
        "ts": _now(), "session": session_id,
        "event": "session_start", "domain": domain, "provider": provider,
    })


def log_tool_call(
    session_id: str, turn: int, tool_name: str, input_keys: list[str]
) -> None:
    """Log which tool was called and what input keys were provided (not values)."""
    _write({
        "ts": _now(), "session": session_id,
        "event": "tool_call", "turn": turn,
        "tool": tool_name, "input_keys": input_keys,
    })


def log_tool_result(
    session_id: str, turn: int, tool_name: str, ok: bool, error: str = ""
) -> None:
    _write({
        "ts": _now(), "session": session_id,
        "event": "tool_result", "turn": turn,
        "tool": tool_name, "ok": ok,
        **({"error": error} if error else {}),
    })


def log_llm_call(
    session_id: str,
    turn: int,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    stop_reason: str,
) -> None:
    _write({
        "ts": _now(), "session": session_id,
        "event": "llm_call", "turn": turn,
        "provider": provider, "model": model,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "stop_reason": stop_reason,
    })


def log_unsafe_output(session_id: str, turn: int, findings: list[str]) -> None:
    _write({
        "ts": _now(), "session": session_id,
        "event": "unsafe_output_blocked", "turn": turn,
        "findings": findings,
    })


def log_session_end(session_id: str, turns_used: int, outcome: str) -> None:
    _write({
        "ts": _now(), "session": session_id,
        "event": "session_end",
        "turns_used": turns_used, "outcome": outcome,
    })
