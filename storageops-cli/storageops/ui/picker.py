"""Interactive session picker for /resume command.

Displays a searchable, filterable list of past sessions with metadata.
Keyboard navigation: ↑/↓ move, Enter select, Ctrl+D delete, / search, Esc cancel.
"""
from __future__ import annotations

import os
import sys
import termios
import tty
from typing import Any

from storageops.core.session import Session, SessionEntry
from storageops.ui.terminal import c, dim, bold, green, red, cyan, yellow, is_tty, hr


def pick_session(query: str = "") -> SessionEntry | None:
    """Show interactive picker, return selected session or None."""
    sessions = Session.list_sessions(limit=30, query=query if query else None)
    if not sessions:
        print(f"\n  {dim('No sessions found.')}\n")
        return None

    if not is_tty() or not sys.stdin.isatty():
        # Non-interactive: return most recent
        return sessions[0] if sessions else None

    return _interactive_picker(sessions)


def _interactive_picker(sessions: list[SessionEntry]) -> SessionEntry | None:
    """Full interactive picker with keyboard navigation."""
    idx = 0
    search = ""
    scroll = 0
    visible = min(len(sessions), 20)
    searching = False

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        while True:
            # Render
            _render_picker(sessions, idx, scroll, search, visible)

            key = _read_key(fd)
            if key is None:
                continue

            if key == "up":
                if idx > 0:
                    idx -= 1
                    if idx < scroll:
                        scroll = idx
                searching = False

            elif key == "down":
                if idx < len(sessions) - 1:
                    idx += 1
                    if idx >= scroll + visible:
                        scroll = idx - visible + 1
                searching = False

            elif key == "enter":
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                return sessions[idx]

            elif key == "escape":
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                return None

            elif key in ("ctrl_d", "delete"):
                # Confirm delete
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                sid = sessions[idx].session_id
                print(f"\n  {yellow('Delete')} {bold(sid)}? (y/N): ", end="", flush=True)
                response = sys.stdin.readline().strip().lower()
                if response == "y":
                    Session(sid).delete()
                    print(f"  {green('✓')} Deleted\n")
                else:
                    print(f"  {dim('Cancelled')}\n")
                tty.setcbreak(fd)

            elif key == "/":
                searching = True
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                print(f"\r\033[K  {dim('Search:')} ", end="", flush=True)
                search = sys.stdin.readline().strip()
                # Re-fetch with search
                sessions = Session.list_sessions(limit=30, query=search if search else None)
                idx = 0
                scroll = 0
                visible = min(len(sessions), 20)
                if not sessions:
                    print(f"\n  {dim('No results for:')} {search}\n")
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    return None
                tty.setcbreak(fd)

            elif key.startswith("char:"):
                char = key[5:]
                if searching:
                    search += char
                else:
                    search = char
                    searching = True
                # Filter sessions by prefix match on name/domain/summary
                filtered = [
                    s for s in sessions
                    if search.lower() in (s.name or "").lower()
                    or search.lower() in s.domain.lower()
                    or search.lower() in s.summary.lower()
                ]
                if filtered:
                    sessions = filtered
                    idx = 0
                    scroll = 0
                    visible = min(len(sessions), 20)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _read_key(fd: int) -> str | None:
    """Read a single keypress. Returns None if no input."""
    try:
        ch = os.read(fd, 1)
        if not ch:
            return None
    except (OSError, ValueError):
        return None

    b = ch[0]
    if b == 10 or b == 13:  # Enter
        return "enter"
    if b == 27:  # Escape
        # Check for escape sequences
        try:
            nxt = os.read(fd, 2)
            if nxt == b"[A":
                return "up"
            if nxt == b"[B":
                return "down"
            if nxt == b"[C":
                return "right"
            if nxt == b"[D":
                return "left"
            if nxt == b"[3":
                os.read(fd, 1)  # consume ~
                return "delete"
        except (OSError, ValueError):
            pass
        return "escape"
    if b == 127:  # Backspace
        return "backspace"
    if b == 4:  # Ctrl-D
        return "ctrl_d"
    if b == ord("/"):
        return "/"
    if 32 <= b < 127:
        return f"char:{chr(b)}"
    return None


def _render_picker(
    sessions: list[SessionEntry],
    idx: int,
    scroll: int,
    search: str,
    visible: int,
) -> None:
    """Render the picker UI."""
    # Clear screen area (move up)
    print(f"\033[{visible + 4}A\033[J", end="")

    print()
    if search:
        print(f"  {dim('Search:')} {bold(search)}")
    else:
        print(f"  {bold('Recent sessions')}  {dim(f'({len(sessions)} total)')}")
        print(f"  {dim('/ to search  ↑↓ to navigate  Enter to select  Ctrl+D to delete  Esc to cancel')}")
    print(hr(70))

    end = min(scroll + visible, len(sessions))
    for i in range(scroll, end):
        s = sessions[i]
        ts = (s.created or s.updated or "")[:16].replace("T", " ")
        domain_display = (s.domain or "unknown").replace("_", " ")[:18]

        # Session name or summary
        label = s.name or s.summary or ""
        label = label[:60].replace("\n", " ")

        if i == idx:
            print(f"  {green('▸')} ", end="")
        else:
            print("    ", end="")

        mark = green("✓") if s.has_assistant else dim("·")
        sid_short = s.session_id[:8]

        print(f"{mark}  {bold(sid_short)}  {dim(ts)}  {cyan(domain_display)}")
        print(f"       {dim(label)}")

    print()
