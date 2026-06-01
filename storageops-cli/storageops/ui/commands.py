"""Slash command handlers for the interactive REPL.

All slash commands (/help, /resume, /clear, etc.) are dispatched here.
Each handler receives the session and optional arguments.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from storageops.core.session import Session, SessionEntry
from storageops.ui.display import StreamDisplay
from storageops.ui.picker import pick_session
from storageops.ui.terminal import (
    c, dim, bold, green, red, cyan, yellow, magenta, hr, ok, err, is_tty,
)


# ── Session state (imported by repl.py) ──────────────────────────────


def show_help() -> None:
    groups = [
        ("Session", [
            ("/help",     "Show this command list"),
            ("/history",  "Show command history  (/history <N> for last N)"),
            ("/resume",   "Browse and select past sessions"),
            ("/clear",    "Save current session and start fresh"),
            ("/new",      "Save current and immediately start new session"),
            ("/name",     "Name the current session  (/name <name>)"),
            ("/session",  "Show current session details"),
            ("/editor",   "Open $EDITOR for long prompts or paste logs"),
            ("/view",     "Browse the last report in a pager (less)"),
        ]),
        ("Config", [
            ("/config",   "View or set configuration  (/config set <key> <val>)"),
            ("/setup",    "Re-run setup wizard (API key, Pi install)"),
            ("/doctor",   "Environment health check"),
            ("/update",   "Download latest Pi binary and reinstall skills"),
            ("/verbose",  "Toggle verbose mode (show full thinking text)"),
        ]),
        ("Memory", [
            ("/memory",   "Browse past diagnostic cases  (/memory search <query>)"),
        ]),
        ("Exit", [
            ("/exit",     "Exit StorageOps"),
        ]),
    ]
    print()
    for group_name, cmds in groups:
        print(f"  {dim(group_name)}")
        for cmd, desc in cmds:
            print(f"    {cyan(cmd):<18}  {dim(desc)}")
        print()
    print(f"  {dim('Tip: $ cmd runs shell commands  ·  @file attaches files  ·  /editor for long input')}")
    print()


def show_status(session: Session) -> None:
    print()
    print(f"  {bold('Session')}   {dim(session.id)}")
    if session.name and session.name != session.id:
        print(f"  {bold('Name')}      {session.name}")
    print(f"  {bold('Turns')}     {session.user_turns}")
    print(f"  {bold('Domain')}    {cyan(session.domain)}")
    print(f"  {bold('Path')}      {dim(str(session.path))}")

    try:
        from storageops.config import get_provider, get_pi_command, get_api_key
        provider = get_provider()
        pi_cmd = get_pi_command()
        pi_ok = bool(shutil.which(pi_cmd))
        key_ok = bool(get_api_key())
        print(f"  {bold('Provider')}  {provider}")
        print(f"  {bold('Pi')}        {green('ready') if pi_ok else red('not found')}")
        print(f"  {bold('API key')}   {green('configured') if key_ok else yellow('missing')}")
    except Exception:
        pass
    print()


def show_history(history_lines: list[str], n: int = 20) -> None:
    if not history_lines:
        print(f"\n  {dim('No history yet.')}\n")
        return
    print()
    entries = history_lines[-n:]
    for i, line in enumerate(entries, max(1, len(history_lines) - n + 1)):
        preview = line[:100].replace("\n", " ")
        print(f"  {dim(str(i).rjust(4))}  {dim(preview)}")
    print()


def open_editor(session: Session) -> str | None:
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"
    if editor == "vim" and not shutil.which("vim"):
        editor = "nano"

    hint = (
        "# Write your prompt or paste log content above.\n"
        "# Lines starting with # are ignored.\n"
        "# Save and exit to send.  Exit without saving to cancel.\n"
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", prefix="storageops-editor-",
        delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(hint)
        tmp.write("\n")
        tmp_path = tmp.name

    try:
        result = subprocess.call([editor, tmp_path])
    except FileNotFoundError:
        print(f"  {red('✗')}  Editor not found: {editor}")
        print(f"  {dim('Set $EDITOR or install vim/nano.')}")
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        return None

    if result != 0:
        print(f"  {yellow('⊘')}  Editor exited with code {result}")
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        return None

    content = Path(tmp_path).read_text(encoding="utf-8", errors="replace")
    try:
        Path(tmp_path).unlink()
    except OSError:
        pass

    lines = [l for l in content.splitlines() if not l.strip().startswith("#")]
    text = "\n".join(lines).strip()
    if not text:
        print(f"  {dim('⊘')}  Empty prompt (cancelled)")
        return None
    print(f"  {green('✓')}  {dim(f'{len(text)} chars from editor')}")
    return text


def view_report(session: Session) -> None:
    import re
    # Find last assistant message
    last_assistant = None
    for evt in reversed(session.events):
        if hasattr(evt, "text") and evt.text:
            last_assistant = evt.text
            break
    if not last_assistant:
        print(f"\n  {dim('No report to view yet.')}\n")
        return

    # Strip YAML frontmatter
    report = re.sub(r'^---\n.*?\n---\n?', '', last_assistant, flags=re.DOTALL).strip()

    # Try syntax highlighting
    try:
        from pygments import highlight
        from pygments.lexers import MarkdownLexer
        from pygments.formatters import Terminal256Formatter
        report = highlight(report, MarkdownLexer(),
                          Terminal256Formatter(style="monokai"))
    except ImportError:
        pass

    pager = os.environ.get("PAGER", "less -R")
    try:
        proc = subprocess.Popen(pager.split(), stdin=subprocess.PIPE, text=True)
        proc.communicate(input=report)
    except FileNotFoundError:
        lines = report.split("\n")[:50]
        for line in lines:
            print(f"  {line}")
        print(f"  {dim(f'… ({len(report.split(chr(10)))} lines. Install less for full pager.)')}")
        print()


def handle_config(parts: list[str]) -> None:
    from storageops import config as cfg_mod
    if len(parts) >= 4 and parts[1] == "set":
        key = parts[2]
        val = " ".join(parts[3:])
        if key == "api_key":
            from storageops.config import detect_provider_from_key
            cfg_mod.update(api_key=val, provider=detect_provider_from_key(val))
            print(f"\n  {green('✓')}  api_key updated\n")
        else:
            cfg_mod.update(**{key: val})
            print(f"\n  {green('✓')}  {key} = {val}\n")
        return

    cfg = cfg_mod.load()
    provider = cfg.get("provider", "unknown")
    key_set = bool(cfg.get("api_key"))
    pi_cmd = cfg.get("pi_command", dim("default"))
    print()
    print(f"  {bold('provider')}    {cyan(provider)}")
    print(f"  {bold('api_key')}     {green('configured') if key_set else yellow('missing')}")
    print(f"  {bold('pi_command')}  {pi_cmd}")
    print()


def handle_memory(parts: list[str]) -> None:
    if len(parts) >= 3 and parts[1] == "search":
        query = " ".join(parts[2:])
        results = Session.search(query, limit=10)
        if not results:
            print(f"\n  {dim('No results for:')} {query}\n")
            return
        print()
        for r in results:
            ts = (r.created or "")[:16].replace("T", " ")
            domain = r.domain.replace("_", " ")[:20]
            label = r.name or r.summary or ""
            print(f"  {cyan(domain)}  {dim(ts)}")
            if label:
                print(f"  {dim(label[:80])}")
            print()
        return

    # List recent
    sessions = Session.list_sessions(limit=10)
    if not sessions:
        print(f"\n  {dim('No cases in memory yet.')}\n")
        return
    print()
    for r in sessions:
        ts = (r.created or "")[:10]
        domain = r.domain.replace("_", " ")[:25]
        label = (r.name or r.summary or "")[:60]
        print(f"  {cyan(domain):<26} {dim(label):<60} {dim(ts)}")
    print()
    print(f"  {dim('/memory search <query> to search')}\n")
