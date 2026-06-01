"""
Interactive REPL loop for StorageOps.

Provides slash commands, multi-line input, shell execution,
and file path resolution.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from storageops.session import Session, create, load, list_all
from storageops.agent import converse
from storageops.display import Display


PROMPT = "\033[1;36mstorageops>\033[0m "


def _read_line(prompt: str = "") -> str | None:
    """Read one line of input. Returns None on EOF/KeyboardInterrupt."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def _read_multiline(prompt: str = PROMPT) -> str | None:
    """Read possibly-multi-line input. Alt+Enter or Esc+Enter for newline."""
    lines: list[str] = []
    first = True
    while True:
        p = prompt if first else "... "
        first = False
        try:
            line = input(p)
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        # Check if line ends with continuation marker
        # Ctrl+J = newline, Esc+Enter = ALT+Enter = \033 + newline
        if line.endswith("\033") or line.rstrip().endswith("\\"):
            clean = line.rstrip().rstrip("\033").rstrip("\\")
            lines.append(clean)
            continue

        lines.append(line)
        return "\n".join(lines)


def _resolve_filepath(token: str) -> str:
    """Resolve @file references to file contents."""
    path = Path(token[1:]).expanduser()
    if path.is_file():
        try:
            content = path.read_text(encoding="utf-8")
            # Truncate very large files
            if len(content) > 50000:
                content = content[:50000] + "\n... [file truncated at 50KB]"
            return f"[File: {path}]\n\n{content}"
        except Exception as exc:
            return f"[Error reading {path}: {exc}]"
    return token  # Not found, pass through


def _resolve_at_files(text: str) -> str:
    """Replace @file tokens with file contents."""
    import re

    def _replace(m):
        token = m.group(0)
        resolved = _resolve_filepath(token)
        return resolved

    return re.sub(r"@\S+", _replace, text)


def repl() -> None:
    """Main REPL entry point."""
    display = Display()

    # Create initial session
    session = create(cwd=os.getcwd())
    display.show_banner(session_id=session.id)

    while True:
        # Read input
        user_input = _read_multiline()
        if user_input is None:
            print("\nGoodbye!")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            _handle_slash(session, user_input, display)
            continue

        # Shell commands
        if user_input.startswith("$"):
            cmd = user_input[1:].strip()
            _run_shell(cmd, display)
            continue

        # Resolve @file references
        user_input = _resolve_at_files(user_input)

        # Main conversation
        try:
            converse(session, user_input, display)
        except Exception as exc:
            display.show_error(f"Conversation error: {exc}")


# ── Slash Commands ────────────────────────────────────────────────────

def _handle_slash(session: Session, cmd_line: str, display: Display) -> None:
    """Dispatch slash commands."""
    parts = shlex.split(cmd_line)
    if not parts:
        return
    cmd = parts[0].lstrip("/").lower()
    args = parts[1:]

    if cmd == "exit" or cmd == "quit":
        print("Goodbye!")
        sys.exit(0)

    elif cmd == "resume":
        if args:
            sid = args[0]
            loaded = load(sid)
            if loaded:
                nonlocal_session(loaded, display)
            else:
                display.show_error(f"Session not found: {sid}")
        else:
            _session_picker(display)

    elif cmd == "history":
        _show_history(session, display)

    elif cmd == "clear":
        new_s = create(cwd=os.getcwd())
        nonlocal_session(new_s, display)
        display.show_slash_result(f"New session: {new_s.id[:8]}...")

    elif cmd == "session":
        meta = session.meta()
        display.show_slash_result(
            f"Session: {meta.get('id', session.id)[:8]}...\n"
            f"  Created: {meta.get('created', '?')[:19]}\n"
            f"  Turns: {meta.get('turns', 0)}\n"
            f"  Summary: {meta.get('summary', '(none)')[:100]}"
        )

    elif cmd == "search":
        query = " ".join(args) if args else ""
        results = list_all(query=query)
        if results:
            for r in results[:10]:
                sid = r.get("id", "")[:8]
                summary = (r.get("summary") or "")[:60]
                display.show_slash_result(f"  {sid}... {summary}")
        else:
            display.show_slash_result("No sessions found.")

    elif cmd == "fork":
        # Create new session with history from current
        new_s = create(cwd=os.getcwd())
        # Copy existing events
        for ev in session.events():
            new_s.append(ev)
        new_s.sync_meta()
        nonlocal_session(new_s, display)
        display.show_slash_result(f"Forked to: {new_s.id[:8]}...")

    else:
        display.show_error(f"Unknown command: /{cmd}")


# ── Helpers ───────────────────────────────────────────────────────────

_session: Session | None = None


def nonlocal_session(new_s: Session, display: Display) -> None:
    """Update the repl module's session reference."""
    import storageops.repl as repl_mod
    repl_mod._session = new_s


def _session_picker(display: Display) -> None:
    """Interactive session picker."""
    results = list_all()[:20]
    if not results:
        display.show_slash_result("No sessions found.")
        return

    for i, r in enumerate(results):
        sid = r.get("id", "")[:8]
        summary = (r.get("summary") or "(no summary)")[:60]
        turns = r.get("turns", 0)
        display.show_slash_result(f"  [{i}] {sid}... ({turns}t) {summary}")

    try:
        choice = input("Resume which session? [0]: ").strip()
        idx = int(choice) if choice else 0
        if 0 <= idx < len(results):
            sid = results[idx]["id"]
            loaded = load(sid)
            if loaded:
                nonlocal_session(loaded, display)
                display.show_slash_result(f"Resumed session: {sid[:8]}...")
    except (ValueError, KeyboardInterrupt):
        pass


def _show_history(session: Session, display: Display) -> None:
    """Show session history summary."""
    events = session.events()
    display.show_slash_result(f"Session {session.id[:8]}... — {len(events)} events")
    for ev in events:
        t = ev.get("type", "?")
        if t == "session":
            continue
        role = ev.get("role", "")
        if role == "user" or t == "user_turn":
            prompt = ev.get("prompt", ev.get("content", ""))[:80]
            display.show_slash_result(f"  👤 {prompt}")
        elif role == "assistant" or t == "text_delta":
            text = ev.get("text", ev.get("content", ""))[:80]
            if text:
                display.show_slash_result(f"  🤖 {text}")
        elif t == "tool_call":
            display.show_slash_result(f"  ⚙ {ev.get('name', '?')}")
        elif t == "error":
            display.show_slash_result(f"  ✗ {ev.get('message', '?')[:80]}")


def _run_shell(cmd: str, display: Display) -> None:
    """Execute a shell command and show output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.stdout:
            display.show_slash_result(result.stdout.rstrip())
        if result.stderr:
            display.show_error(result.stderr.rstrip())
    except subprocess.TimeoutExpired:
        display.show_error("Command timed out (30s)")
    except Exception as exc:
        display.show_error(str(exc))
