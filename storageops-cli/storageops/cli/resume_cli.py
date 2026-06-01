"""CLI: resume command."""
from __future__ import annotations

import argparse

from storageops.core.session import Session
from storageops.ui.picker import pick_session
from storageops.ui.terminal import bold, dim, green, cyan, red, is_tty


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume a past diagnostic session."""
    from storageops.ui.repl import run_repl

    session_id = getattr(args, "session_id", None)
    show_list = getattr(args, "list", False)

    if session_id:
        run_repl(resume_session=session_id)
        return

    sessions = Session.list_sessions(limit=20)
    if not sessions:
        print()
        print("  No past sessions found.")
        print(dim("  Start a new session with: storageops"))
        print()
        return

    # Default: resume most recent
    if not show_list:
        run_repl(resume_session=sessions[0].session_id)
        return

    # --list: interactive picker
    entry = pick_session()
    if entry:
        run_repl(resume_session=entry.session_id)
