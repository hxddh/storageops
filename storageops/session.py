"""
Append-only JSONL session with sidecar meta.json.

Sessions live at ~/.storageops/sessions/<uuid>.jsonl
Metadata at ~/.storageops/sessions/<uuid>.meta.json

JSONL format:
  Line 1: {"type":"session","id":"<uuid>","created":"<iso>"}
  Line N: Pi event JSON (one per line, raw from Pi stdout)

meta.json: {id, created, updated, cwd, domain, name, summary,
             turns, has_assistant, provider, model}
"""
from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path.home() / ".storageops" / "sessions"


def _ensure_dir() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def new_session_id() -> str:
    return str(uuid.uuid4())


def create(cwd: str = "", domain: str = "", name: str = "",
           provider: str = "", model: str = "") -> Session:
    """Create a new session and return it."""
    _ensure_dir()
    sid = new_session_id()
    now = datetime.now(timezone.utc).isoformat()
    jl_path = SESSIONS_DIR / f"{sid}.jsonl"
    meta_path = SESSIONS_DIR / f"{sid}.meta.json"

    header = {"type": "session", "id": sid, "created": now}
    _write_line(jl_path, header)

    meta = {
        "id": sid,
        "created": now,
        "updated": now,
        "cwd": cwd,
        "domain": domain,
        "name": name,
        "summary": "",
        "turns": 0,
        "has_assistant": False,
        "provider": provider,
        "model": model,
    }
    _write_json(meta_path, meta)

    return Session(sid)


def load(session_id: str) -> Session | None:
    """Load a session by EXACT UUID (not prefix match)."""
    _ensure_dir()
    jl_path = SESSIONS_DIR / f"{session_id}.jsonl"
    if not jl_path.exists():
        return None
    return Session(session_id)


def list_all(query: str | None = None) -> list[dict]:
    """List all sessions, optionally filtering by FTS-like substring search.

    Scans meta.json files. If query is provided, also searches JSONL content
    for matching keywords.
    """
    _ensure_dir()
    results: list[dict] = []
    for mp in sorted(SESSIONS_DIR.glob("*.meta.json"), reverse=True):
        try:
            with mp.open(encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        if query:
            q = query.lower()
            # Search meta fields
            match = (
                q in (meta.get("name") or "").lower()
                or q in (meta.get("summary") or "").lower()
                or q in (meta.get("domain") or "").lower()
            )
            # Also search JSONL content
            if not match:
                jl_path = SESSIONS_DIR / f"{meta.get('id','')}.jsonl"
                if jl_path.exists():
                    try:
                        content = jl_path.read_text(encoding="utf-8")
                        match = q in content.lower()
                    except OSError:
                        pass
            if not match:
                continue

        results.append(meta)
    return results


class Session:
    """Append-only JSONL session with sidecar meta.json."""

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self._jl_path = SESSIONS_DIR / f"{session_id}.jsonl"
        self._meta_path = SESSIONS_DIR / f"{session_id}.meta.json"
        if not self._jl_path.exists():
            raise FileNotFoundError(f"Session {session_id} not found: {self._jl_path}")

    def append(self, event: dict) -> None:
        """Append one event dict as a JSON line. fsync after every write."""
        _write_line(self._jl_path, event)
        self._bump_updated()

    def events(self) -> list[dict]:
        """Return all events including the header line as dicts."""
        return _read_jsonl(self._jl_path)

    def replay(self) -> list[dict]:
        """Extract user/assistant messages for LLM context from JSONL events.

        Skips the header line (type:session) and system/internal events.
        Returns list of {role, content} dicts.
        """
        messages: list[dict] = []
        for ev in self.events():
            if ev.get("type") == "session":
                continue
            role = ev.get("role", "")
            content = ev.get("content", "")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})
            elif ev.get("type") == "user_turn" and "prompt" in ev:
                messages.append({"role": "user", "content": ev["prompt"]})
            elif ev.get("type") == "assistant_message" and "text" in ev:
                messages.append({"role": "assistant", "content": ev["text"]})
        return messages

    def meta(self) -> dict:
        """Read and return the current meta.json contents."""
        if self._meta_path.exists():
            try:
                with self._meta_path.open(encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def sync_meta(self) -> dict:
        """Compute meta from JSONL: summary, turns count, domain detection.

        summary = first assistant text found in events
        turns = count of user_turn events
        """
        events = self.events()
        meta = self.meta()
        meta["updated"] = datetime.now(timezone.utc).isoformat()
        meta["turns"] = sum(1 for e in events if e.get("role") == "user"
                            or e.get("type") == "user_turn")

        # summary = first assistant text
        if not meta.get("summary"):
            for ev in events:
                text = ""
                if ev.get("role") == "assistant" and ev.get("content"):
                    text = str(ev["content"])
                elif ev.get("type") == "assistant_message" and ev.get("text"):
                    text = str(ev["text"])
                elif ev.get("type") == "text_delta" and ev.get("text"):
                    text = str(ev["text"])
                if text:
                    # Take first 200 chars as summary
                    meta["summary"] = text[:200]
                    # Detect domain from YAML frontmatter
                    if "category:" in text[:500]:
                        import re
                        m = re.search(r'category:\s*(\S+)', text[:500])
                        if m and not meta.get("domain"):
                            meta["domain"] = m.group(1)
                    break

        meta["has_assistant"] = any(
            e.get("role") == "assistant"
            or e.get("type") in ("assistant_message", "text_delta")
            for e in events
        )

        self._write_meta(meta)
        return meta

    def delete(self) -> None:
        """Delete both the JSONL and meta.json files."""
        self._jl_path.unlink(missing_ok=True)
        self._meta_path.unlink(missing_ok=True)

    def _bump_updated(self) -> None:
        """Quickly update 'updated' in meta.json without full sync."""
        meta = self.meta()
        meta["updated"] = datetime.now(timezone.utc).isoformat()
        self._write_meta(meta)

    def _write_meta(self, meta: dict) -> None:
        _write_json(self._meta_path, meta)


# ── Internal helpers ──────────────────────────────────────────────────

def _write_line(path: Path, obj: dict) -> None:
    """Append a JSON line and fsync."""
    line = json.dumps(obj, ensure_ascii=False, default=str) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def _write_json(path: Path, obj: dict) -> None:
    """Atomically write a JSON file (write to temp + rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    tmp.rename(path)


def _read_jsonl(path: Path) -> list[dict]:
    """Read all JSON lines from a file."""
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
