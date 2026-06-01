"""CLI: audit command."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from storageops.ui.terminal import c, bold, dim, green, yellow, red, cyan, hr


def cmd_audit(args: argparse.Namespace) -> None:
    from storageops.audit_reader import list_sessions, get_session, compute_stats

    if args.audit_action == "stats":
        stats = compute_stats()
        fmt = getattr(args, "format", "human")
        if fmt == "json":
            print(json.dumps(stats, indent=2, ensure_ascii=False))
            return
        print()
        print(bold("Audit Stats"))
        print(hr())
        print(f"  Sessions:      {stats.get('sessions', 0)}")
        print(f"  Domains:       {', '.join(f'{k} ({v})' for k, v in (stats.get('domains') or {}).items())}")
        print(f"  Outcomes:      {', '.join(f'{k} ({v})' for k, v in (stats.get('outcomes') or {}).items())}")
        rate = stats.get("pi_success_rate")
        if rate is not None:
            print(f"  Pi success:    {rate*100:.0f}%")
        print(f"  Redactions:    {stats.get('total_redactions', 0)}")
        tools = stats.get("tool_frequency", {})
        if tools:
            top = list(tools.items())[:5]
            print(f"  Top tools:     {', '.join(f'{t}×{c}' for t, c in top)}")
        print()
        return

    if args.audit_action == "show":
        events = get_session(args.session_id)
        if not events:
            print(f"{red('✗')} No events for session {args.session_id!r}", file=sys.stderr)
            sys.exit(1)
        print()
        print(bold(f"Session: {args.session_id}"))
        print(hr())
        for ev in events:
            ts = ev.get("ts", "")[:19].replace("T", " ")
            event = ev.get("event", "?")
            extra = ""
            if event == "pi_result":
                extra = f"  ok={ev.get('ok')} redacted={ev.get('redaction_count')} events={ev.get('event_count')}"
            elif event == "tool_call":
                extra = f"  [{ev.get('turn')}] {ev.get('tool')} {ev.get('input_keys', [])}"
            elif event == "tool_result":
                status = "ok" if ev.get("ok") else f"err={ev.get('error')}"
                extra = f"  [{ev.get('turn')}] {ev.get('tool')} → {status}"
            elif event in ("session_start", "session_end"):
                extra = f"  {ev.get('domain')} runtime={ev.get('runtime')} {ev.get('outcome', '')}"
            elif event == "memory_save":
                extra = f"  {ev.get('domain')} → {ev.get('root_cause')}"
            print(f"  {dim(ts)}  {cyan(event)}{dim(extra)}")
        print()
        return

    # list
    sessions = list_sessions(limit=args.limit)
    fmt = getattr(args, "format", "human")
    if fmt == "json":
        print(json.dumps({"ok": True, "count": len(sessions), "sessions": sessions},
                         indent=2, ensure_ascii=False))
        return

    if not sessions:
        print()
        print("  No sessions.")
        print()
        return

    print()
    print(bold(f"Audit — {len(sessions)} session(s)"))
    print(hr(70))
    for s in sessions:
        ts = s["ts"]
        domain = s["domain"]
        outcome = s["outcome"]
        outcome_c = green(outcome) if outcome == "success" else yellow(outcome)
        pi_ok = s.get("pi_ok")
        ok_mark = (green("✓") if pi_ok else red("✗")) if pi_ok is not None else dim("·")
        print(f"  {dim(ts)}  {ok_mark}  {cyan(domain):<32} {outcome_c}")
        if getattr(args, "verbose", False):
            tools = ", ".join(sorted(set(s.get("tools", [])))) or "-"
            print(f"               tools: {dim(tools)}")
    print()
