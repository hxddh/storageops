"""CLI: memory command — uses new Session.search()."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from storageops.core.session import Session
from storageops.ui.terminal import c, bold, dim, green, yellow, cyan, hr


def cmd_memory(args: argparse.Namespace) -> None:
    action = args.memory_action or "list"

    if action == "search":
        _cmd_memory_search(args)
    elif action == "save":
        _cmd_memory_save(args)
    elif action == "export":
        _cmd_memory_export(args)
    elif action == "import":
        _cmd_memory_import(args)
    else:
        _cmd_memory_list(args)


def _cmd_memory_list(args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "human")
    results = Session.list_sessions(limit=getattr(args, "limit", 20))

    if fmt == "json":
        print(json.dumps({"ok": True, "count": len(results), "cases": [r.to_dict() for r in results]},
                         indent=2, ensure_ascii=False))
        return

    if not results:
        print()
        print("  No past cases in memory.")
        print(dim("  Run 'storageops diagnose <file>' to build memory automatically."))
        print()
        return

    print()
    print(bold(f"Memory — {len(results)} case(s)"))
    print(hr(70))
    for entry in results:
        ts = (entry.created or "")[:19].replace("T", " ")
        domain = entry.domain.replace("_", " ")
        label = entry.name or entry.summary or ""
        print(f"  {dim(ts)}  {cyan(domain)}")
        if label:
            print(f"            {dim(label[:80])}")
        print()


def _cmd_memory_search(args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "human")
    query = " ".join(args.query)
    results = Session.search(query, limit=getattr(args, "limit", 5))

    if fmt == "json":
        print(json.dumps({"query": query, "count": len(results),
                          "results": [r.to_dict() for r in results]},
                         indent=2, ensure_ascii=False))
        return

    print()
    print(bold(f"Memory Search: '{query}'"))
    print(hr(60))
    if not results:
        print("  No matching cases found.")
        print()
        return
    for entry in results:
        ts = (entry.created or "")[:10]
        domain = entry.domain.replace("_", " ")
        label = entry.name or entry.summary or ""
        print(f"  {dim(ts)}  {cyan(domain)}")
        if label:
            print(f"             {dim(label[:80])}")
        print()


def _cmd_memory_save(args: argparse.Namespace) -> None:
    # Manual memory save is deprecated in favor of auto-save
    # Still supported for backward compat
    import uuid
    domain = getattr(args, "domain", "general") or "general"
    root_cause = getattr(args, "root_cause", "manual") or "manual"
    summary = getattr(args, "summary", "") or ""
    keywords = getattr(args, "keywords", "") or ""
    if isinstance(keywords, str) and keywords:
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    else:
        keywords = []
    session_id = f"manual-{str(uuid.uuid4())[:8]}"

    # Create a minimal session and save it
    s = Session(session_id)
    from storageops.core.event import UserMessage, AssistantMessage
    s.append(UserMessage(text=summary[:200]))
    s.append(AssistantMessage(text=f"Root cause: {root_cause}\nSummary: {summary}"))
    s.set_name(root_cause[:50])
    s.save()

    print(f"  {green('✓')} Case saved  [{session_id[:8]}]  {domain}  →  {root_cause}")


def _cmd_memory_export(args: argparse.Namespace) -> None:
    output_path = getattr(args, "output", None) or "storageops-memory-export.jsonl"
    count = 0
    sessions_dir = Session._sessions_dir() if hasattr(Session, '_sessions_dir') else None
    # List all and export
    sessions = Session.list_sessions(limit=1000)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in sessions:
            s = Session.load(entry.session_id)
            if s:
                for evt in s.events:
                    from storageops.core.event import event_to_json
                    f.write(json.dumps(event_to_json(evt), ensure_ascii=False) + "\n")
                count += 1
    print(f"  {green('✓')} Exported {count} session(s) to {output_path}")


def _cmd_memory_import(args: argparse.Namespace) -> None:
    path = getattr(args, "input_file", None)
    if not path or not Path(path).exists():
        print(f"  {red('✗')} File not found: {path}", file=sys.stderr)
        sys.exit(1)
    imported = 0
    with open(path, encoding="utf-8") as f:
        session: Session | None = None
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            from storageops.core.event import event_from_json, SessionMeta
            evt = event_from_json(obj)
            if isinstance(evt, SessionMeta):
                if session:
                    session.save()
                    imported += 1
                session = Session(evt.id)
                session._meta = evt
            elif evt and session:
                session.append(evt)
        if session:
            session.save()
            imported += 1
    print(f"  {green('✓')} Imported {imported} session(s)")
