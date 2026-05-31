"""Interactive REPL — Pi Coding Agent-style S3 diagnostic interface."""
from __future__ import annotations

import os
import re
import sys
import select as _select
import tempfile
import time
import threading
from pathlib import Path
from typing import Any

from storageops.session import DiagnosticSession

_IS_TTY       = sys.stdout.isatty()
_IS_INPUT_TTY = sys.stdin.isatty()

# ── ANSI helpers ──────────────────────────────────────────────────────

def _c(text: str, *codes: str) -> str:
    return ("\033[" + ";".join(codes) + "m" + text + "\033[0m") if _IS_TTY else text

def _bold(t: str) -> str:   return _c(t, "1")
def _dim(t: str) -> str:    return _c(t, "2")
def _green(t: str) -> str:  return _c(t, "32")
def _yellow(t: str) -> str: return _c(t, "33")
def _red(t: str) -> str:    return _c(t, "31")
def _cyan(t: str) -> str:   return _c(t, "36")

def _hr(w: int = 60) -> str:
    return _dim("─" * w)


# ── Slash commands ────────────────────────────────────────────────────

_SLASH_CMDS = [
    "/help", "/resume", "/clear", "/status",
    "/config", "/memory", "/update",
    "/doctor", "/setup", "/verbose", "/exit",
]

_SLASH_CMD_HELP = {
    "/help":    "Show this command list",
    "/resume":  "Load a past session",
    "/clear":   "Clear context and start a fresh session",
    "/status":  "Show session info and configuration",
    "/config":  "View or change configuration  (/config set <key> <val>)",
    "/memory":  "Browse past cases  (/memory search <query>)",
    "/update":  "Download latest Pi binary and reinstall skills",
    "/doctor":  "Run environment health check",
    "/setup":   "Re-run setup wizard",
    "/verbose": "Toggle verbose mode (show tool calls)",
    "/exit":    "Exit StorageOps",
}


# ── Banner ────────────────────────────────────────────────────────────

def _make_banner() -> str:
    provider = ""
    try:
        from storageops.config import get_provider, get_api_key
        if get_api_key():
            provider = f"  {_dim(get_provider())}"
    except Exception:
        pass
    hint = _dim("type / for commands  ·  Ctrl+C to interrupt  ·  /exit to quit")
    return f"{_bold('StorageOps')}{provider}  ·  {hint}"


# ── Live progress (spinner + tool calls) ─────────────────────────────

def _summarize_tool_result(event: dict[str, Any]) -> str:
    """Extract a brief human-readable summary from a tool_result event."""
    content = event.get("content") or event.get("result") or event.get("output") or {}
    if isinstance(content, str):
        try:
            import json as _json
            content = _json.loads(content)
        except Exception:
            return content[:60].replace("\n", " ") if content else ""

    if not isinstance(content, dict):
        return ""

    if "ok" in content and not content.get("ok"):
        err = str(content.get("error", ""))[:50]
        return f"error: {err}" if err else "failed"

    snippets: list[str] = []
    for key in ("records", "transfers", "errors", "requests", "signals", "findings"):
        v = content.get(key)
        if isinstance(v, list) and v:
            snippets.append(f"{len(v)} {key}")
        elif isinstance(v, int) and v:
            snippets.append(f"{v} {key}")
    for key in ("root_cause_type", "root_cause", "domain", "bottleneck"):
        v = content.get(key)
        if isinstance(v, str) and v:
            snippets.append(v.replace("_", " ")[:30])
            break
    for key in ("confidence",):
        v = content.get(key)
        if isinstance(v, (int, float)):
            snippets.append(f"{v:.0%}")
    return "  ".join(snippets[:3])


class _LiveProgress:
    """
    Progress display during Pi execution.

    Normal mode:  spinner + elapsed time
    Verbose mode: tool calls printed inline as  ⏺  tool_name  ·  brief_result
    """

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, verbose: bool = False):
        self._verbose = verbose
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._pending_tool: str | None = None

    def __enter__(self):
        if _IS_TTY and not self._verbose:
            self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if _IS_TTY and self._thread.is_alive():
            self._thread.join(timeout=1)
        if _IS_TTY:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def on_event(self, event: dict[str, Any]) -> None:
        if not _IS_TTY:
            return

        typ = str(event.get("type") or event.get("event") or "").lower()

        tool_name = (
            event.get("tool_name")
            or event.get("name")
            or (event.get("function") or {}).get("name")
            or (event.get("tool") or {}).get("name")
        )
        if tool_name or typ in ("tool_use", "tool_call", "function_call"):
            name = str(tool_name or typ)
            if self._verbose:
                with self._lock:
                    self._pending_tool = name
                    sys.stdout.write(f"\r\033[K  {_dim('⏺')}  {_cyan(name):<32}")
                    sys.stdout.flush()
            return

        if typ in ("tool_result", "function_result") and self._verbose and self._pending_tool:
            summary = _summarize_tool_result(event)
            with self._lock:
                if summary:
                    sys.stdout.write(f"  {_dim(summary)}\n")
                else:
                    sys.stdout.write("\n")
                sys.stdout.flush()
                self._pending_tool = None
            return

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            elapsed = time.monotonic() - self._start
            frame = self._FRAMES[i % len(self._FRAMES)]
            sys.stdout.write(
                f"\r  {_cyan(frame)}  {_dim(f'Analyzing…  {elapsed:.0f}s')}"
            )
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1


# ── First-run inline configure ────────────────────────────────────────

def _find_bundled_skills() -> Path | None:
    pkg = Path(__file__).parent / "_skills"
    if pkg.exists():
        return pkg
    repo = Path(__file__).resolve().parents[3] / "agents" / "skills"
    if repo.exists():
        return repo
    return None


def _install_prerequisites_silently() -> None:
    """Install Pi and skills silently if missing. Called before asking for API key."""
    import json
    import shutil
    from storageops import pi_installer
    from storageops.config import get_workdir, update as _cfg_update

    # Pi: install if not found
    try:
        from storageops.config import get_pi_command
        pi_found = bool(shutil.which(get_pi_command())) or pi_installer.pi_bin_path().exists()
    except Exception:
        pi_found = False

    if not pi_found:
        sys.stdout.write(f"  {_dim('·')}  Pi Coding Agent  installing…")
        sys.stdout.flush()
        try:
            dest = pi_installer.download_pi()
            pi_installer.ensure_path_entry()
            sys.stdout.write(f"\r\033[K  {_green('✓')}  Pi Coding Agent  {_dim(str(dest))}\n")
            _cfg_update(pi_command=str(dest))
        except RuntimeError as exc:
            sys.stdout.write(f"\r\033[K  {_yellow('!')}  Pi Coding Agent  {_dim(str(exc))}\n")
        sys.stdout.flush()

    # Skills: copy if missing (silent)
    try:
        workdir = get_workdir()
        workdir.mkdir(parents=True, exist_ok=True)
        skills_dst = workdir / "skills"
        if not skills_dst.exists():
            bundled = _find_bundled_skills()
            if bundled:
                shutil.copytree(str(bundled), str(skills_dst))
                _cfg_update(skills_dir=str(skills_dst))
        # Pi settings.json
        pi_settings = workdir / ".pi" / "settings.json"
        if not pi_settings.exists():
            pi_settings.parent.mkdir(parents=True, exist_ok=True)
            pi_settings.write_text(
                json.dumps({"skills": ["../skills"], "enableSkillCommands": True}, indent=2) + "\n",
                encoding="utf-8",
            )
    except Exception:
        pass


def _first_run_configure() -> None:
    """
    Inline first-run: install Pi silently, then ask for API key once.
    No wizard, no provider picker, no confirmation prompts.
    """
    import getpass
    from storageops.config import detect_provider_from_key, update as _cfg_update

    print()
    _install_prerequisites_silently()
    print()
    print(f"  {_bold('Paste your API key to get started.')}")
    print(f"  {_dim('Anthropic:  console.anthropic.com/settings/api-keys')}")
    print(f"  {_dim('OpenAI:     platform.openai.com/api-keys')}")
    print()
    try:
        key = getpass.getpass(f"  {_dim('API key:')} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print(f"  {_dim('Set ANTHROPIC_API_KEY or OPENAI_API_KEY to continue.')}")
        print()
        return
    if key:
        provider = detect_provider_from_key(key)
        _cfg_update(provider=provider, api_key=key)
        print(f"  {_green('✓')}  {_dim(provider + '  ·  configured')}")
    else:
        print(f"  {_dim('No key entered.')}")
        print(f"  {_dim('Set ANTHROPIC_API_KEY or OPENAI_API_KEY to continue.')}")
    print()


# ── Readline tab completion ───────────────────────────────────────────

def _init_readline() -> None:
    try:
        import readline

        def _completer(text: str, state: int) -> str | None:
            if text.startswith("/"):
                matches = [c + " " for c in _SLASH_CMDS if c.startswith(text)]
                return matches[state] if state < len(matches) else None
            return None

        def _display_matches(substitution: str, matches: list[str], longest: int) -> None:
            print()
            for m in matches:
                cmd = m.strip()
                desc = _SLASH_CMD_HELP.get(cmd, "")
                print(f"  {_cyan(cmd):<22}  {_dim(desc)}")
            print()
            readline.redisplay()

        readline.set_completer(_completer)
        readline.set_completion_display_matches_hook(_display_matches)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n")
    except ImportError:
        pass


# ── Input reading ─────────────────────────────────────────────────────

def _read_input() -> str | None:
    """
    Read one logical user input.

    Interactive: single Enter submits. Paste detection collects buffered lines
    so multi-line pastes arrive as one message.
    Pipe mode: read all of stdin.
    Returns None on EOF/Ctrl+D (exit signal).
    """
    if not _IS_INPUT_TTY:
        data = sys.stdin.read()
        return data if data.strip() else None

    prompt = f"{_cyan('>') if _IS_TTY else '>'} "
    try:
        line = input(prompt)
    except EOFError:
        return None

    # Paste detection: collect any buffered lines that arrived together
    lines = [line]
    try:
        while True:
            r, _, _ = _select.select([sys.stdin], [], [], 0)
            if not r:
                break
            next_line = sys.stdin.readline()
            if not next_line:
                break
            lines.append(next_line.rstrip("\n"))
    except Exception:
        pass

    return "\n".join(lines)


def _expand_file_refs(text: str) -> tuple[str, list[str]]:
    """Replace @path references with file contents. Returns (expanded_text, errors)."""
    errors: list[str] = []

    def _replace(m: re.Match) -> str:
        path = Path(m.group(1)).expanduser()
        if not path.exists():
            errors.append(f"{_red('✗')}  file not found: {path}")
            return m.group(0)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return f"[{path.name}]\n{content}"
        except OSError as exc:
            errors.append(f"{_red('✗')}  cannot read {path}: {exc}")
            return m.group(0)

    expanded = re.sub(r'@([^\s]+)', _replace, text)
    return expanded, errors


# ── Slash command display ─────────────────────────────────────────────

def _print_slash_menu() -> None:
    print()
    print(f"  {_bold('Commands')}")
    for cmd, desc in _SLASH_CMD_HELP.items():
        print(f"  {_cyan(cmd):<22}  {_dim(desc)}")
    print()


def _print_status(session: DiagnosticSession) -> None:
    import shutil
    print()
    print(f"  {_bold('Session')}   {_dim(session.session_id)}")
    turns = len([t for t in session.turns if t.role == "user"])
    print(f"  {_bold('Turns')}     {turns}")
    try:
        from storageops.config import get_provider, get_pi_command, get_api_key
        provider = get_provider()
        pi_cmd = get_pi_command()
        pi_ok = bool(shutil.which(pi_cmd))
        key_ok = bool(get_api_key())
        pi_str = _green("ready") if pi_ok else _red("not found  — run /setup")
        key_str = _green("configured") if key_ok else _yellow("missing  — run /setup")
        print(f"  {_bold('Provider')}  {provider}")
        print(f"  {_bold('Pi')}        {pi_str}")
        print(f"  {_bold('API key')}   {key_str}")
    except Exception:
        pass
    verbose_str = _green("on") if session.verbose else _dim("off")
    print(f"  {_bold('Verbose')}   {verbose_str}  {_dim('(/verbose to toggle)')}")
    print()


# ── Session resume picker ─────────────────────────────────────────────

def _handle_resume(current: DiagnosticSession) -> DiagnosticSession:
    """
    Show recent sessions, let user pick one to load.
    Returns the loaded session (or current if cancelled).
    """
    sessions = DiagnosticSession.list_sessions(limit=20)
    if not sessions:
        print(f"\n  {_dim('No past sessions found.')}\n")
        return current

    print()
    for i, s in enumerate(sessions, 1):
        ts      = s["ts"][:16].replace("T", " ")
        domain  = (s["domain"] or "unknown").replace("_", " ")
        preview = (s["preview"] or "")[:60].replace("\n", " ")
        mark    = _green("✓") if s.get("has_assistant") else _dim("·")
        print(f"  {_dim(str(i)+'.'):<5}{mark}  {_bold(s['session_id'])}  {_dim(ts)}  {_cyan(domain)}")
        if preview:
            print(f"         {_dim(preview)}")
    print()

    if not _IS_INPUT_TTY:
        return current

    try:
        raw = input(f"  Load [1–{len(sessions)}] or session ID (Enter to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return current

    if not raw:
        return current

    try:
        idx = int(raw) - 1
        if 0 <= idx < len(sessions):
            target_id = sessions[idx]["session_id"]
        else:
            print(f"  {_red('✗')}  Invalid choice\n")
            return current
    except ValueError:
        target_id = raw

    loaded = DiagnosticSession.load(target_id)
    if loaded is None:
        print(f"  {_red('✗')}  Session not found: {target_id}\n")
        return current

    user_turns = len([t for t in loaded.turns if t.role == "user"])
    last = next((t for t in reversed(loaded.turns) if t.role == "user"), None)
    print(f"\n  {_dim('Loaded')}  {_bold(loaded.session_id)}  {_dim(f'·  {user_turns} turn(s)')}")
    if last:
        print(f"  {_dim(last.content[:80].replace(chr(10), ' '))}")
    print()
    return loaded


# ── Config handler ────────────────────────────────────────────────────

def _handle_config(parts: list[str]) -> None:
    from storageops import config as cfg_mod
    if len(parts) >= 4 and parts[1] == "set":
        key = parts[2]
        val = " ".join(parts[3:])
        if key == "api_key":
            from storageops.config import detect_provider_from_key
            cfg_mod.update(api_key=val, provider=detect_provider_from_key(val))
            print(f"\n  {_green('✓')}  api_key updated  ·  provider auto-detected\n")
        else:
            cfg_mod.update(**{key: val})
            print(f"\n  {_green('✓')}  {key} = {val}\n")
        return
    cfg = cfg_mod.load()
    provider  = cfg.get("provider", "anthropic")
    raw_key   = cfg.get("api_key", "") or ""
    key_str   = ("*" * 8 + raw_key[-4:]) if len(raw_key) > 8 else (_green("set") if raw_key else _yellow("not set  — /setup to configure"))
    pi_cmd    = cfg.get("pi_command", _dim("default"))
    workdir   = cfg.get("workdir",   _dim("~/.storageops"))
    print()
    print(f"  {_bold('provider')}    {_cyan(provider)}")
    print(f"  {_bold('api_key')}     {key_str}")
    print(f"  {_bold('pi_command')}  {pi_cmd}")
    print(f"  {_bold('workdir')}     {workdir}")
    print(f"\n  {_dim('/config set <key> <value> to change')}\n")


# ── Memory handler ─────────────────────────────────────────────────────

def _handle_memory(parts: list[str]) -> None:
    try:
        from storageops.memory_store import list_cases, search_cases
    except ImportError:
        print(f"\n  {_red('✗')}  memory_store not available\n")
        return

    if len(parts) >= 2 and parts[1] == "search":
        query = " ".join(parts[2:]).strip()
        if not query:
            print(f"\n  {_dim('Usage: /memory search <query>')}\n")
            return
        results = search_cases(query, top_k=5)
        if not results:
            print(f"\n  {_dim('No results for:')} {query}\n")
            return
        print()
        for r in results:
            ts      = (r.get("timestamp") or "")[:16].replace("T", " ")
            domain  = (r.get("domain") or "unknown").replace("_", " ")
            summary = (r.get("summary") or "")[:80]
            print(f"  {_cyan(domain)}  {_dim(ts)}")
            if summary:
                print(f"  {_dim(summary)}")
            print()
        return

    cases = list_cases(limit=10)
    if not cases:
        print(f"\n  {_dim('No cases in memory yet.')}\n")
        return
    print()
    for c in cases:
        ts      = (c.get("timestamp") or "")[:16].replace("T", " ")
        domain  = (c.get("domain") or "unknown").replace("_", " ")
        summary = (c.get("summary") or "")[:72]
        rc      = c.get("root_cause_type") or ""
        print(f"  {_cyan(domain)}  {_dim(ts)}")
        if rc:
            print(f"  {_dim(rc)}")
        if summary:
            print(f"  {_dim(summary)}")
        print()
    print(f"  {_dim('/memory search <query> to search by keyword')}\n")


# ── Response display ──────────────────────────────────────────────────

def _print_result(result, *, elapsed: float | None = None, session_id: str | None = None) -> None:
    if not result.ok:
        print()
        err = result.error or "Unknown error"
        _pi_missing = any(kw in err.lower() for kw in (
            "not found", "no such file", "filenotfounderror",
            "command not found", "permission denied", "pi: not found",
        ))
        if _pi_missing:
            print(f"  {_red('Pi Agent not found.')}")
            print(
                f"  {_dim('Run')} {_bold('storageops setup')} "
                f"{_dim('to install Pi, or type')} {_bold('/setup')} {_dim('here.')}"
            )
        else:
            print(f"  {_red('Diagnosis failed')}")
            print(f"  {_dim(err)}")
        print()
        return

    report = result.report_markdown.strip()
    if not report:
        print(f"  {_yellow('No report generated.')}")
        return

    fm_rc   = re.search(r'^root_cause_type:\s*(\S+)', report, re.MULTILINE)
    fm_conf = re.search(r'^confidence:\s*([\d.]+)',   report, re.MULTILINE)
    fm_sev  = re.search(r'^severity:\s*(\S+)',        report, re.MULTILINE)

    print()
    print(_hr(56))
    if fm_rc:
        sev_str  = fm_sev.group(1).upper() if fm_sev else ""
        conf_str = f"{float(fm_conf.group(1)):.0%}" if fm_conf else ""
        sev_color = (
            _red    if sev_str in ("HIGH", "CRITICAL") else
            _yellow if sev_str == "MEDIUM" else
            _dim
        )
        print(
            f"  {_bold(fm_rc.group(1).replace('_', ' '))}  "
            f"{sev_color(sev_str)}  {_dim(conf_str)}"
        )
    print(_hr(56))
    print()

    body = re.sub(r'^---\n.*?\n---\n?', '', report, flags=re.DOTALL).strip()
    print(body)
    print()

    footer_parts: list[str] = []
    if elapsed is not None:
        footer_parts.append(f"{elapsed:.0f}s")
    if session_id:
        footer_parts.append(f"session {session_id}")
    if footer_parts and _IS_TTY:
        print(_dim("  " + "  ·  ".join(footer_parts)))
        print()


# ── Turn runner ───────────────────────────────────────────────────────

def _run_turn(text: str, session: DiagnosticSession) -> bool:
    """Send one turn to Pi. Returns True on success."""
    from storageops.runtime import AgentRunOptions, PiRpcRuntime
    from storageops.config import get_pi_command

    session.add_evidence(text)
    session.add_turn("user", text)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="storageops-session-",
        delete=False, encoding="utf-8",
    ) as tmp:
        tmp.write(session.accumulated_evidence)
        tmp_path = tmp.name

    progress = _LiveProgress(verbose=session.verbose)
    t_start = time.monotonic()

    options = AgentRunOptions(
        runtime="pi",
        stream=False,
        max_turns=10,
        timeout_seconds=600,
        verbose=session.verbose,
        pi_command=get_pi_command(),
        event_callback=progress.on_event,
    )

    try:
        with progress:
            result = PiRpcRuntime(options).run(tmp_path)
    except KeyboardInterrupt:
        print(f"\n  {_dim('Interrupted.')}\n")
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        return False
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass

    elapsed = time.monotonic() - t_start
    session.add_turn("assistant", result.report_markdown or result.error or "")
    _print_result(result, elapsed=elapsed, session_id=session.session_id)

    if result.ok:
        try:
            session.save()
        except OSError:
            pass
        return True

    return False


# ── Main REPL ─────────────────────────────────────────────────────────

def run_repl(initial_text: str | None = None, resume_session: str | None = None) -> None:
    """Start the interactive diagnostic session (Pi Coding Agent style)."""
    _init_readline()

    # Load or create session
    if resume_session:
        session = DiagnosticSession.load(resume_session)
        if session is None:
            print(f"  {_red('✗')}  Session not found: {resume_session}")
            session = DiagnosticSession()
        if _IS_TTY:
            print(_make_banner())
            print()
        if session.turns:
            user_turns = len([t for t in session.turns if t.role == "user"])
            last = next((t for t in reversed(session.turns) if t.role == "user"), None)
            print(f"  {_dim('Resumed')}  {_bold(session.session_id)}  {_dim(f'·  {user_turns} turn(s)')}")
            if last:
                preview = last.content[:80].replace("\n", " ")
                print(f"  {_dim(preview)}")
            print()
        else:
            print(f"  {_dim('Session')} {_bold(session.session_id)} {_dim('is empty.')}")
            print()
    else:
        session = DiagnosticSession()
        if _IS_TTY:
            print(_make_banner())
            print(f"  {_dim('Session')}  {_bold(session.session_id)}")
            print()

    # First-run: if no API key, configure inline (like Claude Code / Pi)
    if _IS_TTY and _IS_INPUT_TTY and not initial_text:
        from storageops.config import get_api_key
        if not get_api_key():
            _first_run_configure()

    # One-shot mode (pipe or direct argument)
    if initial_text:
        expanded, errs = _expand_file_refs(initial_text)
        for e in errs:
            print(e)
        _run_turn(expanded, session)
        return

    # Interactive loop
    while True:
        try:
            text = _read_input()
        except KeyboardInterrupt:
            print(f"\n  {_dim('Interrupted. Type /exit to quit.')}\n")
            continue

        if text is None:
            # EOF / Ctrl+D
            if session.turns:
                try:
                    session.save()
                except OSError:
                    pass
            print()
            break

        text = text.strip()
        if not text:
            continue

        first = text.split()[0].lower()

        if first in ("/exit", "/quit") or text.lower() in ("exit", "quit"):
            if session.turns:
                try:
                    session.save()
                    print(f"  {_dim('Session')} {_bold(session.session_id)} {_dim('saved.')}")
                except OSError:
                    pass
            print()
            break

        elif first in ("/help", "/"):
            _print_slash_menu()

        elif first == "/resume":
            session = _handle_resume(session)

        elif first == "/status":
            _print_status(session)

        elif first == "/clear":
            session.reset()
            import uuid
            session.session_id = str(uuid.uuid4())[:8]
            print(f"\n  {_dim('New session')}  {_bold(session.session_id)}\n")

        elif first == "/doctor":
            import argparse
            from storageops.cli import cmd_doctor
            cmd_doctor(argparse.Namespace())

        elif first == "/setup":
            import argparse
            from storageops.cli import cmd_setup
            cmd_setup(argparse.Namespace(pi_command="pi"))

        elif first == "/config":
            _handle_config(text.split())

        elif first == "/memory":
            _handle_memory(text.split())

        elif first == "/update":
            import argparse
            from storageops.cli import cmd_update
            cmd_update(argparse.Namespace(check=False))

        elif first == "/verbose":
            session.verbose = not session.verbose
            state = _green("on") if session.verbose else _dim("off")
            print(f"\n  Verbose: {state}\n")

        else:
            expanded, file_errors = _expand_file_refs(text)
            for err in file_errors:
                print(err)
            try:
                _run_turn(expanded, session)
            except KeyboardInterrupt:
                print(f"\n  {_dim('Interrupted. Type /exit to quit.')}\n")
