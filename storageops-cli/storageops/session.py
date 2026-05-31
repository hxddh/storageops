"""Diagnostic session: accumulates evidence and conversation across turns."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re

from storageops.config import get_workdir


@dataclass
class Turn:
    role: str   # "user" | "assistant"
    content: str


class DiagnosticSession:
    """Holds state for one interactive diagnostic conversation."""

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id: str = session_id or str(uuid.uuid4())[:8]
        self.turns: list[Turn] = []
        self.evidence_blocks: list[str] = []
        self.domain: str | None = None
        self.verbose: bool = False
        self.ts: str = datetime.now(timezone.utc).isoformat()

    # ── Evidence ──────────────────────────────────────────────────────

    def add_evidence(self, text: str) -> None:
        t = text.strip()
        if t:
            self.evidence_blocks.append(t)

    @property
    def accumulated_evidence(self) -> str:
        return "\n\n---\n\n".join(self.evidence_blocks)

    def has_log_content(self, text: str) -> bool:
        """Heuristic: does this look like real log/error output worth running Pi on?"""
        indicators = [
            r'\b(Error|Exception|ERROR|WARN|DEBUG|FATAL|CRITICAL)\b',
            r'\b(AccessDenied|NoSuchKey|InvalidSignature|NoSuchBucket|403|404|500|503)\b',
            r'\b(s3://|arn:aws:|amazonaws\.com|SignatureDoesNotMatch)\b',
            r'(Traceback|stack trace|at com\.|at org\.|\tat )',
            r'"[Cc]ode"\s*:\s*"[A-Z]',
            r'<(Error|Code|Message)>',
            r'(time_total|time_connect|HTTP/\d)',
            r'(rclone v\d|s5cmd|aws-cli)',
        ]
        return any(re.search(p, text) for p in indicators)

    # ── Conversation ──────────────────────────────────────────────────

    def add_turn(self, role: str, content: str) -> None:
        self.turns.append(Turn(role=role, content=content))

    def reset(self) -> None:
        self.turns.clear()
        self.evidence_blocks.clear()
        self.domain = None

    # ── Persistence ───────────────────────────────────────────────────

    @staticmethod
    def _sessions_dir() -> Path:
        d = get_workdir() / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self) -> Path:
        """Persist session to ~/.storageops/sessions/<id>.json."""
        path = self._sessions_dir() / f"{self.session_id}.json"
        data = {
            "session_id": self.session_id,
            "ts": self.ts,
            "updated": datetime.now(timezone.utc).isoformat(),
            "domain": self.domain,
            "verbose": self.verbose,
            "evidence_blocks": self.evidence_blocks,
            "turns": [{"role": t.role, "content": t.content} for t in self.turns],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, session_id: str) -> "DiagnosticSession | None":
        """Load a session by ID. Returns None if not found."""
        path = cls._sessions_dir() / f"{session_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            session = cls(session_id=data["session_id"])
            session.ts = data.get("ts", session.ts)
            session.domain = data.get("domain")
            session.verbose = data.get("verbose", False)
            session.evidence_blocks = data.get("evidence_blocks", [])
            for t in data.get("turns", []):
                session.turns.append(Turn(role=t["role"], content=t["content"]))
            return session
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    @classmethod
    def list_sessions(cls, limit: int = 20) -> list[dict]:
        """Return recent sessions sorted newest-first."""
        sessions_dir = cls._sessions_dir()
        results = []
        for path in sorted(sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(results) >= limit:
                break
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                turns = data.get("turns", [])
                last_user = next(
                    (t["content"][:80] for t in reversed(turns) if t["role"] == "user"), ""
                )
                has_assistant = any(t["role"] == "assistant" for t in turns)
                results.append({
                    "session_id": data["session_id"],
                    "ts": data.get("updated") or data.get("ts", ""),
                    "domain": data.get("domain") or "unknown",
                    "turns": len(turns),
                    "preview": last_user,
                    "has_assistant": has_assistant,
                })
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return results
