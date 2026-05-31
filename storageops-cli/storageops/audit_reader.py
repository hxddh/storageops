"""
Audit log reader for StorageOps sessions.

Reads ~/.storageops/audit.jsonl and provides structured access to session history.
Security: Only reads structural metadata — never logs raw evidence text or tool I/O.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

_AUDIT_FILE = Path.home() / ".storageops" / "audit.jsonl"


def _load_records(path: Path | None = None) -> list[dict]:
    target = path or _AUDIT_FILE
    if not target.exists():
        return []
    records: list[dict] = []
    with target.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def list_sessions(limit: int = 20, path: Path | None = None) -> list[dict]:
    """Return the most recent sessions with per-session token and tool stats."""
    records = _load_records(path)
    starts = [r for r in records if r.get("event") == "session_start"]

    ends: dict[str, dict] = {
        r["session"]: r for r in records if r.get("event") == "session_end"
    }
    llm_by_session: dict[str, list[dict]] = defaultdict(list)
    tools_by_session: dict[str, list[str]] = defaultdict(list)
    for r in records:
        if r.get("event") == "llm_call":
            llm_by_session[r["session"]].append(r)
        elif r.get("event") == "tool_call":
            tools_by_session[r["session"]].append(r.get("tool", ""))

    sessions = []
    for s in starts[-limit:]:
        sid = s["session"]
        end = ends.get(sid, {})
        calls = llm_by_session[sid]
        sessions.append({
            "session_id": sid,
            "ts": s.get("ts", "")[:19].replace("T", " "),
            "domain": s.get("domain", "unknown"),
            "provider": s.get("provider", ""),
            "outcome": end.get("outcome", "in_progress"),
            "turns_used": end.get("turns_used", len(calls)),
            "input_tokens": sum(c.get("input_tokens", 0) for c in calls),
            "output_tokens": sum(c.get("output_tokens", 0) for c in calls),
            "tools": tools_by_session[sid],
        })
    return list(reversed(sessions))


def get_session(session_id: str, path: Path | None = None) -> list[dict]:
    """Return all events for a session in chronological order."""
    records = _load_records(path)
    return [r for r in records if r.get("session") == session_id]


def compute_stats(path: Path | None = None) -> dict:
    """Aggregate statistics across all sessions in the audit log."""
    records = _load_records(path)
    if not records:
        return {"sessions": 0, "total_tokens": 0}

    starts = [r for r in records if r.get("event") == "session_start"]
    ends = [r for r in records if r.get("event") == "session_end"]
    llm_calls = [r for r in records if r.get("event") == "llm_call"]
    tool_calls = [r for r in records if r.get("event") == "tool_call"]
    critiques = [r for r in records if r.get("event") == "critique_turn"]

    total_in = sum(r.get("input_tokens", 0) for r in llm_calls)
    total_out = sum(r.get("output_tokens", 0) for r in llm_calls)
    total_turns = sum(r.get("turns_used", 0) for r in ends)

    return {
        "sessions": len(starts),
        "outcomes": dict(Counter(r.get("outcome", "unknown") for r in ends)),
        "domains": dict(Counter(r.get("domain", "unknown") for r in starts)),
        "providers": dict(Counter(r.get("provider", "") for r in llm_calls)),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_in + total_out,
        "tool_frequency": dict(Counter(r.get("tool", "") for r in tool_calls).most_common()),
        "avg_turns": round(total_turns / max(len(ends), 1), 1),
        "critique_confirmation_rate": (
            round(
                sum(1 for r in critiques if r.get("confirmed")) / len(critiques), 2
            ) if critiques else None
        ),
    }
