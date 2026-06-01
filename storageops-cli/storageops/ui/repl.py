"""Interactive REPL — natural conversational S3 diagnostic interface.

Thin UI layer that:
  1. Reads user input (with history, completion, ghost-text)
  2. Dispatches slash commands to ui/commands.py
  3. Delegates AI turns to core/agent.py
  4. Renders streaming events via ui/display.py

All persistence and agent logic is in core/; this file only handles I/O.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from storageops.core.agent import Agent
from storageops.core.session import Session
from storageops.ui.commands import (
    show_help, show_status, show_history, open_editor, view_report,
    handle_config, handle_memory,
)
from storageops.ui.display import StreamDisplay
from storageops.ui.picker import pick_session
from storageops.ui.terminal import (
    c, dim, bold, green, red, cyan, yellow, hr, err, is_tty,
)

_IS_INPUT_TTY = sys.stdin.isatty()
_HISTORY_MAX = 2000
_HISTORY_LINES: list[str] = []


# ── Banner ────────────────────────────────────────────────────────────

def _banner() -> str:
    provider_str = ""
    try:
        from storageops.config import get_provider, get_api_key
        if get_api_key():
            provider_str = f"  {cyan(get_provider())}"
        else:
            provider_str = f"  {yellow('no api key — /setup')}"
    except Exception:
        pass
    lines = [
        bold("StorageOps"),
        f"{provider_str}",
        "",
        dim("Describe your S3 issue or paste a log file."),
        dim("@file to attach   $ cmd to run   /editor for long prompts   /help for commands"),
    ]
    return "\n".join(lines)


def _prompt() -> str:
    return f"  {c('›', 'cyan')}  " if is_tty() else "> "


# ── Readline setup ───────────────────────────────────────────────────

def _history_file() -> Path:
    from storageops.config import get_workdir
    return get_workdir() / "history"


def _append_history(text: str) -> None:
    if text and text.strip() and not text.strip().startswith("/"):
        if not _HISTORY_LINES or _HISTORY_LINES[-1] != text:
            _HISTORY_LINES.append(text)
            if len(_HISTORY_LINES) > _HISTORY_MAX:
                _HISTORY_LINES[:] = _HISTORY_LINES[-_HISTORY_MAX:]


def _init_readline() -> None:
    try:
        import readline
    except ImportError:
        return

    hist_path = _history_file()
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(str(hist_path))
        for i in range(readline.get_current_history_length()):
            _HISTORY_LINES.append(readline.get_history_item(i + 1))
    except (OSError, FileNotFoundError):
        pass

    import atexit
    def _save() -> None:
        try:
            readline.set_history_length(_HISTORY_MAX)
            readline.write_history_file(str(hist_path))
        except OSError:
            pass
    atexit.register(_save)

    # Tab completion for slash commands and @file
    _SLASH_CMDS = [
        "/help", "/history", "/resume", "/clear", "/new", "/name", "/session",
        "/status", "/config", "/memory", "/update", "/doctor", "/setup",
        "/verbose", "/editor", "/view", "/exit",
    ]

    def _completer(text: str, state: int) -> str | None:
        if text.startswith("/"):
            matches = [c + " " for c in _SLASH_CMDS if c.startswith(text)]
            return matches[state] if state < len(matches) else None
        return None

    readline.set_completer(_completer)
    readline.parse_and_bind("tab: complete")


def _read_input(prompt_text: str) -> str | None:
    if not _IS_INPUT_TTY:
        data = sys.stdin.read()
        return data if data.strip() else None

    try:
        return input(prompt_text)
    except EOFError:
        return None
    except KeyboardInterrupt:
        return None


# ── File expansion ───────────────────────────────────────────────────

def _expand_file_refs(text: str) -> tuple[str, list[str]]:
    errors: list[str] = []

    def _replace(m: re.Match) -> str:
        raw = m.group(1)
        path = Path(raw).expanduser()
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                return f"[{path.name}]\n{content}"
            except OSError as exc:
                errors.append(f"{red('✗')}  cannot read {path}: {exc}")
                return m.group(0)
        # Try glob
        try:
            parent = path.parent if path.is_absolute() else Path.cwd()
            matches = sorted(
                parent.glob(path.name),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            if matches:
                resolved = matches[0]
                content = resolved.read_text(encoding="utf-8", errors="replace")
                errors.append(f"{dim('@')}{raw}{dim(' → ')}{resolved.name}")
                return f"[{resolved.name}]\n{content}"
        except OSError:
            pass
        errors.append(f"{red('✗')}  file not found: {raw}")
        return m.group(0)

    return re.sub(r'@([^\s]+)', _replace, text), errors


# ── Shell handler ────────────────────────────────────────────────────

def _handle_shell(text: str, session: Session) -> None:
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("$"):
            continue
        cmd_str = stripped[1:].strip()
        if not cmd_str:
            continue
        print(f"  {c('$', 'cyan')} {dim(cmd_str)}")
        try:
            result = subprocess.run(
                cmd_str, shell=True, capture_output=True, text=True,
                timeout=15, cwd=str(Path.cwd()),
            )
            output = result.stdout.strip()
            if result.stderr.strip():
                output += "\n" + result.stderr.strip()
            if not output:
                output = f"(exit {result.returncode})"
            summary = output[:200].replace("\n", "\n  ")
            print(f"  {dim(summary)}")
            if len(output) > 200:
                print(f"  {dim(f'… ({len(output)} chars total)')}")
        except subprocess.TimeoutExpired:
            print(f"  {red('✗')}  Command timed out")
        except Exception as exc:
            print(f"  {red('✗')}  {exc}")


# ── Main REPL ────────────────────────────────────────────────────────

def run_repl(initial_text: str | None = None, resume_session: str | None = None) -> None:
    """Start the interactive StorageOps session."""
    global _HISTORY_LINES
    _init_readline()

    # Create or resume session
    session: Session
    if resume_session:
        loaded = Session.load(resume_session)
        if loaded is None:
            print(f"  {red('✗')}  Session not found: {resume_session}")
            session = Session()
        else:
            session = loaded
            if is_tty():
                print(_banner())
                print()
            print(f"  {dim('Resumed')}  {bold(session.id)}  {dim(f'·  {session.user_turns} turn(s)')}")
            if session.name:
                print(f"  {dim(session.name)}")
            print()
    else:
        session = Session()
        if is_tty():
            print(_banner())
            print(f"  {dim('Session')}  {bold(session.id)}  {dim('·  new')}")
            print()

    # First-run configure
    if is_tty() and _IS_INPUT_TTY and not initial_text:
        from storageops.config import get_api_key
        if not get_api_key():
            _first_run_setup()

    agent = Agent(session=session)

    # One-shot mode
    if initial_text:
        _run_one_shot(agent, session, initial_text)
        return

    # Interactive loop
    while True:
        try:
            text = _read_input(_prompt())
        except KeyboardInterrupt:
            print(f"\n  {dim('/exit to quit')}\n")
            continue

        if text is None:
            # EOF
            _save_and_exit(agent, session)
            break

        text = text.strip()
        if not text:
            continue

        first = text.split()[0].lower()

        # ── Shell command ──────────────────────────────────
        if first.startswith("$") and len(first) > 1:
            _append_history(text)
            _handle_shell(text, session)
            continue

        # ── Slash commands ─────────────────────────────────
        if first in ("/exit", "/quit") or text.lower() in ("exit", "quit"):
            _save_and_exit(agent, session)
            break

        elif first in ("/help", "/"):
            show_help()

        elif first == "/history":
            parts = text.split()
            n = 20
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                except ValueError:
                    pass
            show_history(_HISTORY_LINES, n)

        elif first == "/resume":
            parts = text.split()
            if len(parts) > 1:
                target_id = parts[1]
                loaded = Session.load(target_id)
                if loaded:
                    _save_and_exit(agent, session)
                    session = loaded
                    agent = Agent(session=session)
                    print(f"\n  {dim('Resumed')}  {bold(session.id[:8])}  {dim(f'·  {session.user_turns} turn(s)')}")
                    if session.name:
                        print(f"  {dim(session.name)}")
                    print()
                else:
                    print(f"  {red('✗')}  Session not found: {target_id}\n")
            else:
                entry = pick_session()
                if entry:
                    loaded = Session.load(entry.session_id)
                    if loaded:
                        _save_and_exit(agent, session)
                        session = loaded
                        agent = Agent(session=session)
                        print(f"\n  {dim('Resumed')}  {bold(session.id[:8])}  {dim(f'·  {session.user_turns} turn(s)')}")
                        print()

        elif first == "/status":
            show_status(session)

        elif first == "/session":
            show_status(session)

        elif first == "/clear":
            _save_and_exit(agent, session)
            session = Session()
            agent = Agent(session=session)
            print(f"\n  {green('✓')}  New session  {bold(session.id)}\n")

        elif first == "/new":
            _save_and_exit(agent, session)
            session = Session()
            agent = Agent(session=session)
            print(f"\n  {green('✓')}  New session  {bold(session.id)}\n")

        elif first == "/name":
            parts = text.split(maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                name = parts[1].strip()
                session.set_name(name)
                print(f"  {green('✓')}  Session named: {bold(name)}\n")
            else:
                print(f"  {dim('Usage: /name <session name>')}\n")

        elif first == "/doctor":
            from storageops.cli import cmd_doctor
            import argparse
            cmd_doctor(argparse.Namespace())

        elif first == "/setup":
            from storageops.cli import cmd_setup
            import argparse
            cmd_setup(argparse.Namespace(pi_command="pi"))

        elif first == "/config":
            handle_config(text.split())

        elif first == "/memory":
            handle_memory(text.split())

        elif first == "/update":
            from storageops.cli import cmd_update
            import argparse
            cmd_update(argparse.Namespace(check=False))

        elif first == "/view":
            view_report(session)

        elif first == "/verbose":
            _verbose = not _verbose
            state = green("on") if _verbose else dim("off")
            print(f"\n  Verbose: {state}  ({dim('shows full thinking text')})\n")

        elif first == "/editor":
            editor_text = open_editor(session)
            if editor_text:
                _append_history(editor_text)
                expanded, file_errors = _expand_file_refs(editor_text)
                for e in file_errors:
                    print(e)
                _run_turn(agent, session, expanded)

        # ── Normal message ─────────────────────────────────
        else:
            _append_history(text)
            expanded, file_errors = _expand_file_refs(text)
            for e in file_errors:
                print(e)
            _run_turn(agent, session, expanded)


# ── Turn runner ───────────────────────────────────────────────────────

_verbose: bool = False


def _run_turn(agent: Agent, session: Session, text: str) -> None:
    """Execute one turn: send text to agent, stream display, show result."""
    global _verbose

    display = StreamDisplay(verbose=_verbose)

    def _callback(evt: dict) -> None:
        display.on_raw(evt)

    t_start = time.monotonic()
    agent.on_event = _callback

    try:
        events = agent.run(text)
    except KeyboardInterrupt:
        print(f"\n  {yellow('⊘')}  Stopped.\n")
        return

    elapsed = time.monotonic() - t_start

    # Show footer
    if is_tty() and elapsed > 0:
        print()
        parts = [
            f"{elapsed:.0f}s",
            f"session {session.id[:8]}",
        ]
        print(dim("  " + "  ·  ".join(parts)))
        # Find if there's content to view
        for evt in reversed(events):
            if hasattr(evt, "text") and evt.text and len(evt.text) > 1200:
                print(dim("  Type /view to browse the full report in a pager."))
                break
        print()


def _run_one_shot(agent: Agent, session: Session, text: str) -> None:
    """Run a single turn and exit (stdin/non-TTY mode)."""
    expanded, errs = _expand_file_refs(text)
    for e in errs:
        print(e)
    events = agent.run(expanded)
    # Print assistant response
    for evt in events:
        if hasattr(evt, "text") and evt.text:
            print(evt.text)
    agent.runtime.stop()


def _save_and_exit(agent: Agent, session: Session) -> None:
    try:
        session.save()
        if session.user_turns > 0:
            print(f"  {dim('Session')} {bold(session.id)} {dim('saved.')}")
    except OSError:
        pass
    agent.runtime.stop()
    print()


# ── First-run setup ──────────────────────────────────────────────────

def _first_run_setup() -> None:
    import json
    import shutil
    import getpass
    from storageops import pi_installer
    from storageops.config import (
        get_workdir, update as _cfg_update, detect_provider_from_key,
    )

    # Auto-install Pi
    try:
        from storageops.config import get_pi_command
        pi_found = bool(shutil.which(get_pi_command())) or pi_installer.pi_bin_path().exists()
    except Exception:
        pi_found = False

    if not pi_found:
        sys.stdout.write(f"  {dim('·')}  Pi Coding Agent  installing…")
        sys.stdout.flush()
        try:
            dest = pi_installer.download_pi()
            pi_installer.ensure_path_entry()
            sys.stdout.write(f"\r\033[K  {green('✓')}  Pi Coding Agent  {dim(str(dest))}\n")
            _cfg_update(pi_command=str(dest))
        except RuntimeError as exc:
            sys.stdout.write(f"\r\033[K  {yellow('!')}  Pi Coding Agent  {dim(str(exc))}\n")
        sys.stdout.flush()

    # Install skills
    try:
        workdir = get_workdir()
        workdir.mkdir(parents=True, exist_ok=True)
        skills_dst = workdir / "skills"
        if not skills_dst.exists():
            pkg_skills = Path(__file__).parent / "_skills"
            if pkg_skills.exists():
                shutil.copytree(str(pkg_skills), str(skills_dst))
            else:
                repo = Path(__file__).resolve().parents[3] / "agents" / "skills"
                if repo.exists():
                    shutil.copytree(str(repo), str(skills_dst))
            _cfg_update(skills_dir=str(skills_dst))
        pi_settings = workdir / ".pi" / "settings.json"
        if not pi_settings.exists():
            pi_settings.parent.mkdir(parents=True, exist_ok=True)
            pi_settings.write_text(
                json.dumps({"skills": ["../skills"], "enableSkillCommands": True}, indent=2) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass

    print()
    print(f"  {bold('Paste your API key to get started.')}")
    print(f"  {dim('Anthropic:  console.anthropic.com/settings/api-keys')}")
    print(f"  {dim('OpenAI:     platform.openai.com/api-keys')}")
    print()
    try:
        key = getpass.getpass(f"  {dim('API key:')} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print(f"  {dim('Set ANTHROPIC_API_KEY or OPENAI_API_KEY to continue.')}")
        print()
        return
    if key:
        provider = detect_provider_from_key(key)
        _cfg_update(provider=provider, api_key=key)
        print(f"  {green('✓')}  {dim(provider + '  ·  configured')}")
    print()


# ── Module entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    run_repl()
