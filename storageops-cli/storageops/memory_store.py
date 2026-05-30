"""
Persistent case memory for StorageOps agent sessions.

JSONL-based, offline-first, zero external dependencies.
Cases are stored in ~/.storageops/memory.jsonl.
Retrieval uses keyword overlap scoring — no vector embeddings needed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_MEMORY_FILE = Path.home() / ".storageops" / "memory.jsonl"
_MAX_SUMMARY_LEN = 600
_MAX_KEYWORDS = 25

# Common stop words to exclude from keyword matching
_STOP = {
    "the", "a", "an", "is", "in", "of", "to", "and", "or", "for",
    "with", "that", "this", "it", "be", "at", "by", "on", "as",
    "was", "are", "were", "has", "have", "had", "not", "but",
}


def _memory_path() -> Path:
    _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    return _MEMORY_FILE


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r'\w+', text.lower())) - _STOP


def save_case(
    session_id: str,
    domain: str,
    root_cause: str,
    summary: str,
    keywords: list[str] | None = None,
) -> dict:
    """Append a diagnosed case to memory. Returns the saved entry."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "domain": domain,
        "root_cause": root_cause,
        "summary": summary[:_MAX_SUMMARY_LEN],
        "keywords": (keywords or [])[:_MAX_KEYWORDS],
    }
    with _memory_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def search_cases(query: str, domain: str | None = None, top_k: int = 3) -> list[dict]:
    """Return top_k past cases ranked by keyword overlap with query."""
    path = _memory_path()
    if not path.exists():
        return []

    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored: list[tuple[int, dict]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if domain and entry.get("domain") != domain:
                continue

            haystack = " ".join([
                entry.get("summary", ""),
                entry.get("root_cause", ""),
                " ".join(entry.get("keywords", [])),
                entry.get("domain", ""),
            ])
            overlap = len(query_terms & _tokenize(haystack))
            if overlap > 0:
                scored.append((overlap, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


def list_cases(domain: str | None = None, limit: int = 20) -> list[dict]:
    """Return most recent cases, newest first."""
    path = _memory_path()
    if not path.exists():
        return []

    entries: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if domain and entry.get("domain") != domain:
                continue
            entries.append(entry)

    return list(reversed(entries[-limit:]))
