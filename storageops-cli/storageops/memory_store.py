"""
Persistent case memory for StorageOps agent sessions.

JSONL-based, offline-first, zero external dependencies.
Cases are stored in ~/.storageops/memory.jsonl.
Retrieval uses BM25 scoring (k1=1.5, b=0.75) — no vector embeddings needed.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

_MEMORY_FILE = Path.home() / ".storageops" / "memory.jsonl"
_MAX_SUMMARY_LEN = 600
_MAX_KEYWORDS = 25

_STOP = {
    "the", "a", "an", "is", "in", "of", "to", "and", "or", "for",
    "with", "that", "this", "it", "be", "at", "by", "on", "as",
    "was", "are", "were", "has", "have", "had", "not", "but",
}

_BM25_K1 = 1.5
_BM25_B = 0.75


def _memory_path() -> Path:
    _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    return _MEMORY_FILE


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r'\w+', text.lower()) if t not in _STOP]


def _bm25_score(
    query_terms: list[str],
    doc_tokens: list[str],
    all_doc_tokens: list[list[str]],
) -> float:
    """BM25 score for one document against a query."""
    N = len(all_doc_tokens)
    if N == 0 or not query_terms:
        return 0.0
    avg_dl = sum(len(d) for d in all_doc_tokens) / N
    doc_len = len(doc_tokens)
    tf: dict[str, int] = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1

    score = 0.0
    for term in set(query_terms):
        if term not in tf:
            continue
        df = sum(1 for d in all_doc_tokens if term in set(d))
        idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
        tf_norm = (tf[term] * (_BM25_K1 + 1)
                   / (tf[term] + _BM25_K1 * (1 - _BM25_B + _BM25_B * doc_len / max(avg_dl, 1))))
        score += idf * tf_norm
    return score


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
    """Return top_k past cases ranked by BM25 score against the query."""
    path = _memory_path()
    if not path.exists():
        return []

    query_terms = _tokenize(query)
    if not query_terms:
        return []

    entries: list[dict] = []
    doc_texts: list[list[str]] = []
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
            entries.append(entry)
            doc_texts.append(_tokenize(haystack))

    if not entries:
        return []

    scored = [
        (_bm25_score(query_terms, doc_tokens, doc_texts), entry)
        for doc_tokens, entry in zip(doc_texts, entries)
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for score, e in scored[:top_k] if score > 0]


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


def export_cases(output_path: str, domain: str | None = None) -> int:
    """Write matching cases to a JSONL file. Returns the number of cases exported."""
    cases = list_cases(domain=domain, limit=10_000)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for entry in reversed(cases):  # chronological order
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return len(cases)


def import_cases(input_path: str, merge: bool = True) -> tuple[int, int]:
    """Import cases from a JSONL file. Returns (imported_count, skipped_count).

    With merge=True, entries with a duplicate session_id or matching
    domain+root_cause+summary are skipped.
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Import file not found: {input_path}")

    existing: list[dict] = []
    path = _memory_path()
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    existing_ids: set[str] = {e["session_id"] for e in existing if "session_id" in e}
    existing_tuples: set[tuple[str, str, str]] = {
        (e.get("domain", ""), e.get("root_cause", ""), e.get("summary", "")[:100])
        for e in existing
    }

    imported = 0
    skipped = 0
    with src.open(encoding="utf-8") as f, path.open("a", encoding="utf-8") as out:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if merge:
                sid = entry.get("session_id", "")
                key = (entry.get("domain", ""), entry.get("root_cause", ""), entry.get("summary", "")[:100])
                if sid in existing_ids or key in existing_tuples:
                    skipped += 1
                    continue
                existing_ids.add(sid)
                existing_tuples.add(key)
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            imported += 1

    return imported, skipped
