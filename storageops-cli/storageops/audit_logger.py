"""
Audit logger for StorageOps Pi agent sessions.

Writes JSONL records to ~/.storageops/audit.jsonl.
Each record has: ts, session_id, event type, and safe metadata.

Security: Never log raw evidence text, tool inputs/outputs, or user content.
Only log structural metadata (tool names, outcomes, redaction counts).
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


def log_session_start(session_id: str, domain: str, runtime: str = "pi") -> None:
    _write({
        "ts": _now(),
        "session": session_id,
        "event": "session_start",
        "domain": domain,
        "runtime": runtime,
    })


def log_pi_result(
    session_id: str,
    *,
    ok: bool,
    redaction_count: int,
    validation_ok: bool,
    event_count: int,
) -> None:
    """Log the outcome of a Pi RPC call (no raw content — metadata only)."""
    _write({
        "ts": _now(),
        "session": session_id,
        "event": "pi_result",
        "ok": ok,
        "redaction_count": redaction_count,
        "validation_ok": validation_ok,
        "event_count": event_count,
    })


def log_tool_call(session_id: str, turn: int, tool_name: str, input_keys: list[str]) -> None:
    _write({
        "ts": _now(),
        "session": session_id,
        "event": "tool_call",
        "turn": turn,
        "tool": tool_name,
        "input_keys": input_keys,
    })


def log_tool_result(
    session_id: str, turn: int, tool_name: str, ok: bool, error: str = ""
) -> None:
    _write({
        "ts": _now(),
        "session": session_id,
        "event": "tool_result",
        "turn": turn,
        "tool": tool_name,
        "ok": ok,
        **({"error": error} if error else {}),
    })


def log_memory_save(session_id: str, domain: str, root_cause: str) -> None:
    _write({
        "ts": _now(),
        "session": session_id,
        "event": "memory_save",
        "domain": domain,
        "root_cause": root_cause,
    })


def log_session_end(session_id: str, outcome: str) -> None:
    _write({
        "ts": _now(),
        "session": session_id,
        "event": "session_end",
        "outcome": outcome,
    })
