"""
Audit log reader for StorageOps Pi sessions.

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
    """Return the most recent sessions with per-session tool and Pi result stats."""
    records = _load_records(path)
    starts = [r for r in records if r.get("event") == "session_start"]

    ends: dict[str, dict] = {
        r["session"]: r for r in records if r.get("event") == "session_end"
    }
    pi_results: dict[str, dict] = {
        r["session"]: r for r in records if r.get("event") == "pi_result"
    }
    tools_by_session: dict[str, list[str]] = defaultdict(list)
    for r in records:
        if r.get("event") == "tool_call":
            tools_by_session[r["session"]].append(r.get("tool", ""))

    sessions = []
    for s in starts[-limit:]:
        sid = s["session"]
        end = ends.get(sid, {})
        pi = pi_results.get(sid, {})
        sessions.append({
            "session_id": sid,
            "ts": s.get("ts", "")[:19].replace("T", " "),
            "domain": s.get("domain", "unknown"),
            "runtime": s.get("runtime", "pi"),
            "outcome": end.get("outcome", "in_progress"),
            "pi_ok": pi.get("ok"),
            "redaction_count": pi.get("redaction_count", 0),
            "event_count": pi.get("event_count", 0),
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
        return {"sessions": 0}

    starts = [r for r in records if r.get("event") == "session_start"]
    ends = [r for r in records if r.get("event") == "session_end"]
    pi_results = [r for r in records if r.get("event") == "pi_result"]
    tool_calls = [r for r in records if r.get("event") == "tool_call"]

    total_redactions = sum(r.get("redaction_count", 0) for r in pi_results)
    total_events = sum(r.get("event_count", 0) for r in pi_results)

    return {
        "sessions": len(starts),
        "outcomes": dict(Counter(r.get("outcome", "unknown") for r in ends)),
        "domains": dict(Counter(r.get("domain", "unknown") for r in starts)),
        "runtimes": dict(Counter(r.get("runtime", "pi") for r in starts)),
        "pi_success_rate": (
            round(sum(1 for r in pi_results if r.get("ok")) / len(pi_results), 2)
            if pi_results else None
        ),
        "total_redactions": total_redactions,
        "total_pi_events": total_events,
        "tool_frequency": dict(Counter(r.get("tool", "") for r in tool_calls).most_common()),
    }
