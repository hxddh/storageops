"""JSONL-backed session persistence with FTS5 search and context replay.

Sessions are stored as JSONL files in ~/.storageops/sessions/.
Each line is a serialized Event from core/event.py.
A companion sqlite3 FTS5 index provides full-text search across sessions.

Key features:
- Append-only writes (never load full file to append)
- Context replay: read all events, reconstruct conversation for LLM
- Auto-domain detection via auto_detect() on user input
- Session naming, listing, search, delete
"""
from __future__ import annotations

import json
import os
import sqlite3
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storageops.core.event import (
    Event, SessionMeta, UserMessage, AssistantMessage, ThinkBlock,
    ToolCall, ToolResult, TurnStart, TurnEnd,
    event_from_json, event_to_json,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sessions_dir() -> Path:
    from storageops.config import get_workdir
    d = get_workdir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fts_db_path() -> Path:
    return _sessions_dir() / "index.fts.db"


# ── FTS5 helpers ─────────────────────────────────────────────────────

def _ensure_fts() -> sqlite3.Connection:
    db = sqlite3.connect(str(_fts_db_path()))
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
            session_id, name, domain, summary, content,
            tokenize='porter unicode61'
        )
    """)
    db.commit()
    return db


def _fts_upsert(conn: sqlite3.Connection, session_id: str,
                name: str, domain: str, summary: str, content: str) -> None:
    # Delete old entry then insert
    conn.execute("DELETE FROM sessions_fts WHERE session_id = ?", (session_id,))
    conn.execute(
        "INSERT INTO sessions_fts(session_id, name, domain, summary, content) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, name, domain, summary, content),
    )
    conn.commit()


def _fts_delete(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM sessions_fts WHERE session_id = ?", (session_id,))
    conn.commit()


def _fts_search(query: str, limit: int = 20) -> list[str]:
    """Return session_ids matching the query, ranked by BM25."""
    conn = _ensure_fts()
    try:
        rows = conn.execute(
            "SELECT session_id FROM sessions_fts WHERE sessions_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [r[0] for r in rows]
    except sqlite3.OperationalError:
        # FTS query syntax error — fall back to LIKE
        like = "%" + query.replace("'", "''") + "%"
        rows = conn.execute(
            "SELECT session_id FROM sessions_fts WHERE name LIKE ? OR summary LIKE ? "
            "LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [r[0] for r in rows]


# ── Session ──────────────────────────────────────────────────────────

class Session:
    """A single diagnostic session backed by a JSONL file."""

    def __init__(self, session_id: str | None = None) -> None:
        self.id: str = session_id or str(uuid.uuid4())
        self._path: Path = _sessions_dir() / f"{self.id}.jsonl"
        self._events: list[Event] = []
        self._meta: SessionMeta = SessionMeta(
            id=self.id, created=_now_iso(), cwd=str(Path.cwd()),
        )
        self._name: str = ""
        self._domain: str = ""
        self._dirty: bool = False
        self._meta_written: bool = False

    # ── Properties ───────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    @property
    def name(self) -> str:
        return self._name or self.id

    @property
    def domain(self) -> str:
        return self._domain or "unknown"

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    @property
    def user_turns(self) -> int:
        return sum(1 for e in self._events if isinstance(e, UserMessage))

    @property
    def created(self) -> str:
        return self._meta.created

    # ── Append events ────────────────────────────────────────────────

    def append(self, event: Event) -> None:
        """Add an event to the session. Auto-saves to JSONL."""
        self._ensure_meta()  # Write meta before first event
        self._events.append(event)
        self._write_line(event_to_json(event))
        self._dirty = True

        # Track domain from user input
        if isinstance(event, UserMessage) and event.text:
            self._detect_domain(event.text)

    def _detect_domain(self, text: str) -> None:
        if self._domain:
            return
        try:
            from signatures import auto_detect
            detections = auto_detect(text)
            if detections and detections[0].get("domain"):
                self._domain = detections[0]["domain"]
                self._meta.domain = self._domain
                # Update header in JSONL (rewrite first line)
                self._update_meta()
        except Exception:
            pass

    def _write_line(self, obj: dict) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def _ensure_meta(self) -> None:
        """Write the SessionMeta as the first line if not already written."""
        if self._meta_written:
            return
        if not self._path.exists():
            self._write_line(self._meta.to_json())
            self._meta_written = True
            return
        # File exists — check if first line is already meta
        try:
            with open(self._path, encoding="utf-8") as f:
                first = f.readline().strip()
            if first:
                obj = json.loads(first)
                if obj.get("type") == "session_meta":
                    self._meta_written = True
                    return
        except (OSError, json.JSONDecodeError):
            pass
        # Need to prepend meta
        self._prepend_meta()
        self._meta_written = True

    def _prepend_meta(self) -> None:
        """Insert SessionMeta at the beginning of the file."""
        meta_line = json.dumps(self._meta.to_json(), ensure_ascii=False) + "\n"
        lines: list[str] = []
        try:
            with open(self._path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            lines = []
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(meta_line)
            f.writelines(lines)

    def _update_meta(self) -> None:
        """Rewrite the session metadata line (first line only)."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return
        if lines:
            # Only replace if first line is actually session_meta
            try:
                obj = json.loads(lines[0].strip())
                if obj.get("type") == "session_meta":
                    lines[0] = json.dumps(self._meta.to_json(), ensure_ascii=False) + "\n"
                    with open(self._path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
            except json.JSONDecodeError:
                pass

    # ── Save / finalize ──────────────────────────────────────────────

    def save(self) -> Path:
        """Write metadata and flush. Called after each turn."""
        # Ensure metadata line 1 exists
        if not self._path.exists():
            self._write_line(self._meta.to_json())

        # Update FTS index with summary
        summary = self._generate_summary()
        content = self._content_for_fts()
        self._update_meta()
        conn = _ensure_fts()
        _fts_upsert(conn, self.id, self._name, self.domain, summary, content)
        self._dirty = False
        return self._path

    # ── Summary generation ───────────────────────────────────────────

    def _generate_summary(self) -> str:
        """Extract a meaningful summary from the assistant's first response."""
        for evt in self._events:
            if isinstance(evt, AssistantMessage) and evt.text:
                # Take first sentence, up to 100 chars
                text = evt.text.strip()
                # Strip YAML frontmatter
                text = re.sub(r'^---\n.*?\n---\n?', '', text, flags=re.DOTALL)
                # Take first meaningful sentence
                for sentence in re.split(r'(?<=[。.!?！？])\s*', text):
                    sentence = sentence.strip()
                    if len(sentence) > 10:
                        return sentence[:100]
                return text[:100]
        # Fallback: first user message
        for evt in self._events:
            if isinstance(evt, UserMessage) and evt.text:
                return evt.text[:80]
        return ""

    def _content_for_fts(self) -> str:
        """Concatenate all text content for FTS5 indexing."""
        parts: list[str] = []
        for evt in self._events:
            if isinstance(evt, UserMessage):
                parts.append(evt.text)
            elif isinstance(evt, AssistantMessage):
                parts.append(evt.text)
            elif isinstance(evt, ToolCall):
                parts.append(evt.name)
            elif isinstance(evt, ToolResult):
                parts.append(f"{evt.name} {evt.summary}")
        return " ".join(parts)

    # ── Naming ────────────────────────────────────────────────────────

    def set_name(self, name: str) -> None:
        self._name = name
        self._meta.name = name
        self._update_meta()

    # ── Context replay ───────────────────────────────────────────────

    def build_replay_prompt(self) -> str:
        """Build a prompt that replays the full conversation history.

        Returns a string representation of all user/assistant turns that
        can be included in the next prompt sent to the LLM.
        """
        parts: list[str] = []
        for evt in self._events:
            if isinstance(evt, UserMessage) and evt.text:
                parts.append(f"User: {evt.text}")
            elif isinstance(evt, AssistantMessage) and evt.text:
                # Truncate very long responses
                text = evt.text
                if len(text) > 2000:
                    text = text[:2000] + "\n... (truncated)"
                parts.append(f"Assistant: {text}")
            # Tool calls are implicit in the assistant response; skip for brevity
        return "\n\n".join(parts)

    @property
    def needs_new_turn(self) -> bool:
        """True if there's conversation history to replay."""
        return any(isinstance(e, UserMessage) for e in self._events)

    # ── Load / delete ────────────────────────────────────────────────

    @classmethod
    def load(cls, session_id: str) -> "Session | None":
        """Load a session from its JSONL file. Supports prefix matching."""
        path = _sessions_dir() / f"{session_id}.jsonl"
        if not path.exists():
            # Try prefix match
            candidates = sorted(
                _sessions_dir().glob(f"{session_id}*.jsonl"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            if candidates:
                path = candidates[0]
            else:
                return None
        try:
            # Extract the true session ID from the filename (not the prefix)
            true_id = path.stem
            session = cls(session_id=true_id)
            session._path = path  # Override to point at the real file
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    evt = event_from_json(obj)
                    if isinstance(evt, SessionMeta):
                        session._meta = evt
                        session._name = evt.name
                        session._domain = evt.domain
                    elif evt is not None:
                        session._events.append(evt)
            session._dirty = False
            return session
        except OSError:
            return None

    def delete(self) -> None:
        """Delete session file and FTS entry."""
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass
        conn = _ensure_fts()
        _fts_delete(conn, self.id)

    # ── Static helpers ────────────────────────────────────────────────

    @staticmethod
    def list_sessions(limit: int = 20, query: str | None = None) -> list["SessionEntry"]:
        """List recent sessions, optionally filtered by FTS query."""
        sessions_dir = _sessions_dir()

        if query:
            session_ids = _fts_search(query, limit=limit)
        else:
            # Gather all JSONL files, exclude FTS index and orphan prefix-only files
            all_files = sorted(
                sessions_dir.glob("*.jsonl"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            # Filter out orphan prefix-only files (created by pre-fix bug)
            # A valid session file has a full UUID (36 chars); prefix files are shorter
            filtered: list[str] = []
            for p in all_files:
                sid = p.stem
                if len(sid) < 32:
                    # This is a prefix-only orphan — skip it unless it's the only file
                    continue
                filtered.append(sid)
            # Also skip orphan entries: files < 2 lines (only meta, no events)
            session_ids = []
            for sid in filtered:
                p = sessions_dir / f"{sid}.jsonl"
                try:
                    with open(p, encoding="utf-8") as f:
                        line_count = sum(1 for _ in f)
                    if line_count >= 2:
                        session_ids.append(sid)
                except OSError:
                    continue

        results: list[SessionEntry] = []
        for sid in session_ids:
            if len(results) >= limit:
                break
            entry = SessionEntry.from_session_id(sid)
            if entry:
                results.append(entry)
        return results

    @staticmethod
    def search(query: str, limit: int = 10) -> list["SessionEntry"]:
        """Full-text search across all sessions."""
        session_ids = _fts_search(query, limit=limit)
        results: list[SessionEntry] = []
        for sid in session_ids:
            entry = SessionEntry.from_session_id(sid)
            if entry:
                results.append(entry)
        return results

    @staticmethod
    def count() -> int:
        """Total number of valid session files."""
        count = 0
        for p in _sessions_dir().glob("*.jsonl"):
            if len(p.stem) >= 32:
                count += 1
        return count

    @staticmethod
    def cleanup_orphans() -> int:
        """Remove orphaned prefix-only session files (from pre-fix bug).
        Returns count of deleted files."""
        deleted = 0
        for p in _sessions_dir().glob("*.jsonl"):
            stem = p.stem
            # Orphan: short name (< 32 chars, not a full UUID)
            if len(stem) < 32:
                # Check if a full-UUID sibling exists
                full_matches = list(_sessions_dir().glob(f"{stem}-*.jsonl"))
                if full_matches:
                    p.unlink(missing_ok=True)
                    deleted += 1
        return deleted

    @staticmethod
    def prune_old(days: int = 30) -> int:
        """Delete sessions older than N days. Returns count of deleted."""
        import time as _time
        cutoff = _time.time() - days * 86400
        count = 0
        for p in _sessions_dir().glob("*.jsonl"):
            if p.stat().st_mtime < cutoff:
                sid = p.stem
                p.unlink(missing_ok=True)
                conn = _ensure_fts()
                _fts_delete(conn, sid)
                count += 1
        return count


# ── SessionEntry (lightweight, for picker UI) ────────────────────────

class SessionEntry:
    """Lightweight session metadata for the picker. Does not load full events."""

    def __init__(
        self,
        session_id: str,
        name: str = "",
        domain: str = "unknown",
        summary: str = "",
        turns: int = 0,
        created: str = "",
        updated: str = "",
        has_assistant: bool = False,
    ) -> None:
        self.session_id = session_id
        self.name = name
        self.domain = domain
        self.summary = summary
        self.turns = turns
        self.created = created
        self.updated = updated
        self.has_assistant = has_assistant

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "domain": self.domain,
            "summary": self.summary,
            "turns": self.turns,
            "created": self.created,
            "updated": self.updated,
            "has_assistant": self.has_assistant,
        }

    @classmethod
    def from_session_id(cls, session_id: str) -> "SessionEntry | None":
        """Parse just enough from the JSONL header to populate an entry."""
        path = _sessions_dir() / f"{session_id}.jsonl"
        if not path.exists():
            return None
        try:
            stat = path.stat()
            updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

            # Read first line for metadata
            meta: SessionMeta | None = None
            with open(path, encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    try:
                        obj = json.loads(first_line)
                        evt = event_from_json(obj)
                        if isinstance(evt, SessionMeta):
                            meta = evt
                    except json.JSONDecodeError:
                        pass

            # Count user turns and check for assistant
            turns = 0
            has_assistant = False
            last_user: str = ""
            with open(path, encoding="utf-8") as f:
                f.readline()  # Skip meta
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "user_message":
                        turns += 1
                        last_user = obj.get("text", "")
                    if obj.get("type") == "assistant_message":
                        has_assistant = True

            # Build summary from meta or generate from first assistant
            summary = ""
            if meta:
                name = meta.name
                domain = meta.domain or "unknown"
                created = meta.created
            else:
                name = ""
                domain = "unknown"
                created = ""

            # If no name, try to extract a meaningful summary
            if not name and not summary:
                with open(path, encoding="utf-8") as f:
                    f.readline()  # Skip meta
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("type") == "assistant_message":
                            text = obj.get("text", "")
                            text = re.sub(r'^---\n.*?\n---\n?', '', text, flags=re.DOTALL)
                            for sentence in re.split(r'(?<=[。.!?！？])\s*', text):
                                sentence = sentence.strip()
                                if len(sentence) > 10:
                                    summary = sentence[:100]
                                    break
                            if summary:
                                break
                if not summary:
                    summary = last_user[:80]

            return cls(
                session_id=session_id,
                name=name,
                domain=domain,
                summary=summary,
                turns=turns,
                created=created,
                updated=updated,
                has_assistant=has_assistant,
            )
        except OSError:
            return None
