"""Interactive REPL — natural-language S3 diagnostic agent interface."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import threading
from pathlib import Path
from typing import Any

from storageops.session import DiagnosticSession

_IS_TTY = sys.stdout.isatty()

_SLASH_CMDS = ["/help", "/clear", "/status", "/doctor", "/setup", "/verbose", "/exit"]

_SLASH_CMD_HELP = {
    "/help":    "Show this command list",
    "/clear":   "Clear session and start fresh",
    "/status":  "Show current session info",
    "/doctor":  "Environment health check",
    "/setup":   "Re-run setup wizard",
    "/verbose": "Toggle verbose mode (show tool calls)",
    "/exit":    "Exit",
}


# ── ANSI helpers (safe for non-TTY) ──────────────────────────────────

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


# ── Banner (dynamic — shows provider when configured) ─────────────────

def _make_banner() -> str:
    provider_hint = ""
    try:
        from storageops.config import get_provider, get_api_key
        if get_api_key():
            provider_hint = f"{get_provider()}  ·  "
    except Exception:
        pass
    hint = f"\033[2m{provider_hint}Type / for commands  ·  Ctrl+C or /exit to quit\033[0m"
    return (
        f"\033[1mStorageOps\033[0m  S3 Diagnostic Agent\n"
        f"Describe your issue or paste error logs. "
        f"Use \033[2m@file.log\033[0m to reference a file.\n"
        f"{hint}\n"
    )


_TIPS = """
Tips:
  • Paste log output directly — StorageOps detects it automatically
  • Reference a file:  @/path/to/error.log
  • Type / then Tab to see all commands
  • Empty line submits a multi-line block
"""


# ── Live progress display ─────────────────────────────────────────────

class _LiveProgress:
    """Replaces _Spinner. Shows spinner + elapsed time; in verbose mode shows tool calls."""

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, verbose: bool = False):
        self._verbose = verbose
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._thread = threading.Thread(target=self._spin, daemon=True)

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
        """Display tool call events (verbose mode) or suppress (spinner mode)."""
        if not _IS_TTY:
            return
        # Detect tool call events — Pi may use various field names
        tool_name = (
            event.get("tool_name")
            or event.get("name")
            or (event.get("function") or {}).get("name")
            or (event.get("tool") or {}).get("name")
        )
        typ = str(event.get("type") or event.get("event") or "").lower()
        if tool_name or typ in ("tool_use", "tool_call", "function_call", "tool_result"):
            name = str(tool_name or typ)
            if self._verbose:
                with self._lock:
                    sys.stdout.write(f"\r\033[K  {_dim('›')}  {_cyan(name)}\n")
                    sys.stdout.flush()

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


# ── Setup detection & inline prompts ─────────────────────────────────

def _check_pi_ready() -> tuple[bool, bool]:
    """Return (pi_installed, api_key_configured)."""
    import shutil
    pi_ok = key_ok = False
    try:
        from storageops.config import get_pi_command, get_api_key
        pi_ok = bool(shutil.which(get_pi_command()))
        key_ok = bool(get_api_key())
    except Exception:
        pass
    return pi_ok, key_ok


def _run_first_time_setup() -> None:
    """Full inline setup prompt when Pi is not installed."""
    print()
    print(f"  {_yellow('!')}  Pi Agent is not configured.")
    print(f"  {_dim('AI diagnosis requires Pi. Run setup to get started.')}")
    print()
    try:
        ans = input("  Run setup now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if ans in ("", "y", "yes"):
        print()
        import argparse as _ap
        from storageops.cli import cmd_setup
        cmd_setup(_ap.Namespace(pi_command="pi"))
    else:
        print()
        print(f"  {_dim('Continuing without Pi — AI diagnosis unavailable.')}")
        print(f"  {_dim('Run')} {_bold('storageops setup')} {_dim('when ready.')}")
        print()


def _run_api_key_setup() -> None:
    """Inline prompt when Pi is installed but no API key is configured."""
    print()
    print(f"  {_yellow('!')}  No API key configured.")
    print(f"  {_dim('An Anthropic or OpenAI key is required for AI diagnosis.')}")
    print()
    try:
        ans = input("  Configure API key now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if ans in ("", "y", "yes"):
        print()
        import argparse as _ap
        from storageops.cli import cmd_setup
        cmd_setup(_ap.Namespace(pi_command="pi"))
    else:
        print()
        print(f"  {_dim('Run')} {_bold('storageops setup')} {_dim('to configure your API key.')}")
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

def _read_block() -> list[str]:
    """Collect lines until empty line (double-Enter) or Ctrl+D. Pipe: read all stdin."""
    if not _IS_TTY:
        return sys.stdin.read().splitlines()

    lines: list[str] = []
    prompt_first = "\033[1;36m>\033[0m " if _IS_TTY else "> "
    prompt_cont  = "  "

    while True:
        try:
            line = input(prompt_first if not lines else prompt_cont)
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)

    return lines


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


# ── Evidence checklist hint ───────────────────────────────────────────

_DOMAIN_HINTS: dict[str, list[str]] = {
    "security_iam_policy": [
        "Full error message (including RequestId)",
        "IAM role or user ARN",
        "Action attempted (e.g. s3:GetObject)",
    ],
    "s3_protocol_compatibility": [
        "Error code and message",
        "Provider name and endpoint",
        "SDK or tool version",
    ],
    "performance_throughput": [
        "Observed throughput or timing",
        "Object sizes and count",
        "Tool name and version",
    ],
    "network_endpoint_access": [
        "Endpoint URL or hostname",
        "curl -v or dig output",
        "VPC / PrivateLink details if applicable",
    ],
    "cors_configuration": [
        "Error message",
        "Origin header value",
        "HTTP method",
    ],
    "lifecycle_cost": [
        "Lifecycle configuration XML",
        "Storage class of affected objects",
    ],
}


def _evidence_hint(domain: str) -> str:
    hints = _DOMAIN_HINTS.get(domain, [])
    if not hints:
        return ""
    lines = [f"  {_dim('·')}  {h}" for h in hints]
    return (
        f"\n  {_dim('To improve diagnosis, share:')}\n"
        + "\n".join(lines)
        + "\n"
    )


# ── Slash command helpers ─────────────────────────────────────────────

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
    domain = session.domain or "not classified yet"
    print(f"  {_bold('Domain')}    {domain.replace('_', ' ')}")
    turns = len([t for t in session.turns if t.role == "user"])
    print(f"  {_bold('Turns')}     {turns}")
    try:
        from storageops.config import get_provider, get_pi_command, get_api_key
        provider = get_provider()
        pi_cmd = get_pi_command()
        pi_ok = bool(shutil.which(pi_cmd))
        key_ok = bool(get_api_key())
        pi_str = _green("ready") if pi_ok else _red("not found  — run storageops setup")
        key_str = _green("configured") if key_ok else _yellow("missing  — run storageops setup")
        print(f"  {_bold('Provider')}  {provider}")
        print(f"  {_bold('Pi')}        {pi_str}")
        print(f"  {_bold('API key')}   {key_str}")
    except Exception:
        pass
    verbose_str = _green("on") if session.verbose else _dim("off")
    print(f"  {_bold('Verbose')}   {verbose_str}  {_dim('(/verbose to toggle)')}")
    print()


# ── Response display ──────────────────────────────────────────────────

def _print_result(result) -> None:
    """Display a Pi diagnostic result (AgentRunResult)."""
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

    fm_cat  = re.search(r'^category:\s*(\S+)',        report, re.MULTILINE)
    fm_rc   = re.search(r'^root_cause_type:\s*(\S+)', report, re.MULTILINE)
    fm_conf = re.search(r'^confidence:\s*([\d.]+)',   report, re.MULTILINE)
    fm_sev  = re.search(r'^severity:\s*(\S+)',        report, re.MULTILINE)

    print()
    print(_hr(56))
    if fm_cat and fm_rc:
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


# ── Main REPL loop ────────────────────────────────────────────────────

def run_repl(initial_text: str | None = None, resume_session: str | None = None) -> None:
    """Start the interactive diagnostic REPL."""
    from storageops.runtime import AgentRunOptions, PiRpcRuntime
    from storageops.config import get_pi_command

    _init_readline()

    if resume_session:
        session = DiagnosticSession.load(resume_session)
        if session is None:
            print(f"  {_red('✗')}  Session not found: {resume_session}")
            session = DiagnosticSession()
        else:
            if _IS_TTY:
                print(_make_banner())
            print(
                f"  {_dim('Resumed')}  {_bold(session.session_id)}  "
                f"{_dim(session.domain or 'unknown domain')}"
            )
            if session.turns:
                last = next((t for t in reversed(session.turns) if t.role == "user"), None)
                if last:
                    preview = last.content[:80].replace("\n", " ")
                    print(f"  {_dim('Last:')}  {preview}")
            print()
    else:
        session = DiagnosticSession()
        if _IS_TTY:
            print(_make_banner())

    # ── First-run guard (TTY interactive only) ────────────────────────
    if _IS_TTY and not initial_text:
        pi_ok, key_ok = _check_pi_ready()
        if not pi_ok:
            _run_first_time_setup()
        elif not key_ok:
            _run_api_key_setup()

    def _process(text: str) -> None:
        """Run one diagnostic turn against Pi."""
        session.add_evidence(text)
        session.add_turn("user", text)

        from signatures import auto_detect
        detections = auto_detect(session.accumulated_evidence)
        domain = detections[0]["domain"] if detections else "unknown"
        conf   = detections[0]["confidence"] if detections else 0.0
        session.domain = domain

        if _IS_TTY:
            print(
                f"  {_dim('Domain:')}  {_bold(domain.replace('_', ' '))}  "
                f"{_dim(f'({conf:.0%})')}"
            )

        if not session.has_log_content(session.accumulated_evidence) and not initial_text:
            hint = _evidence_hint(domain)
            print(f"\n  {_dim('Paste your error log or command output below.')}{hint}")
            return

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="storageops-session-",
            delete=False, encoding="utf-8",
        ) as tmp:
            tmp.write(session.accumulated_evidence)
            tmp_path = tmp.name

        progress = _LiveProgress(verbose=session.verbose)

        options = AgentRunOptions(
            runtime="pi",
            stream=_IS_TTY and not session.verbose,  # verbose shows events; stream for non-verbose
            max_turns=10,
            timeout_seconds=600,
            verbose=session.verbose,
            pi_command=get_pi_command(),
            event_callback=progress.on_event,
        )

        try:
            with progress:
                result = PiRpcRuntime(options).run(tmp_path)
        finally:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass

        session.add_turn("assistant", result.report_markdown or result.error or "")
        _print_result(result)
        try:
            session.save()
        except OSError:
            pass

    # ── One-shot mode (pipe / direct argument) ────────────────────────
    if initial_text:
        expanded, errs = _expand_file_refs(initial_text)
        for e in errs:
            print(e)
        _process(expanded)
        return

    # ── Interactive loop ──────────────────────────────────────────────
    while True:
        try:
            lines = _read_block()
        except KeyboardInterrupt:
            print("\nGoodbye.")
            break

        if not lines:
            continue

        text = "\n".join(lines).strip()
        if not text:
            continue

        first = text.split()[0].lower()

        # /exit
        if first in ("/exit", "/quit") or text.lower() in ("exit", "quit"):
            if session.turns:
                try:
                    session.save()
                    print(f"  {_dim('Session')} {_bold(session.session_id)} {_dim('saved.')}")
                except OSError:
                    pass
            print("Goodbye.")
            break

        # /help  or bare /
        elif first in ("/help", "/"):
            _print_slash_menu()
            print(_TIPS)

        # /status
        elif first == "/status":
            _print_status(session)

        # /clear
        elif first == "/clear":
            session.reset()
            print(_dim("  Session cleared.\n"))

        # /doctor
        elif first == "/doctor":
            import argparse
            from storageops.cli import cmd_doctor
            cmd_doctor(argparse.Namespace())

        # /setup
        elif first == "/setup":
            import argparse
            from storageops.cli import cmd_setup
            cmd_setup(argparse.Namespace(pi_command="pi"))

        # /verbose
        elif first == "/verbose":
            session.verbose = not session.verbose
            state = _green("on  — tool calls will be shown") if session.verbose else _dim("off")
            print(f"\n  Verbose: {state}\n")

        else:
            # Regular input — expand file refs and diagnose
            text, file_errors = _expand_file_refs(text)
            for err in file_errors:
                print(err)
            try:
                _process(text)
            except KeyboardInterrupt:
                print(f"\n  {_dim('Interrupted. Type /exit to quit or continue.')}\n")
