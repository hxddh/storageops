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

# Separate stdin (input) from stdout (display) TTY detection.
# stdin may be a pipe (cat log | storageops) while stdout is still a terminal.
_IS_TTY       = sys.stdout.isatty()   # ANSI colours and progress display
_IS_INPUT_TTY = sys.stdin.isatty()    # interactive input vs pipe mode

_SLASH_CMDS = ["/help", "/clear", "/status", "/doctor", "/setup", "/verbose", "/exit"]

_SLASH_CMD_HELP = {
    "/help":    "Show this command list",
    "/clear":   "Clear session and start fresh",
    "/status":  "Show current session info",
    "/doctor":  "Environment health check",
    "/setup":   "Re-run setup wizard",
    "/verbose": "Toggle verbose mode (show tool calls + results)",
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


# ── Banner ────────────────────────────────────────────────────────────

def _make_banner() -> str:
    """Dynamic banner — shows provider when configured."""
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
  • Empty line submits a multi-line block (Ctrl+D also works)
"""


# ── Live progress display ─────────────────────────────────────────────

def _summarize_tool_result(event: dict[str, Any]) -> str:
    """Extract a brief human-readable summary from a tool_result event."""
    content = event.get("content") or event.get("result") or event.get("output") or {}
    if isinstance(content, str):
        # Try to parse as JSON first
        try:
            import json as _json
            content = _json.loads(content)
        except Exception:
            # Return first 60 chars of string
            return content[:60].replace("\n", " ") if content else ""

    if not isinstance(content, dict):
        return ""

    # Common tool output shapes
    if "ok" in content and not content.get("ok"):
        err = str(content.get("error", ""))[:50]
        return f"error: {err}" if err else "failed"

    snippets: list[str] = []
    # Parser outputs
    for key in ("records", "transfers", "errors", "requests", "signals", "findings"):
        v = content.get(key)
        if isinstance(v, list) and v:
            snippets.append(f"{len(v)} {key}")
        elif isinstance(v, int) and v:
            snippets.append(f"{v} {key}")
    # Analyzer outputs
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
    Verbose mode: tool calls printed inline as  ›  tool_name  ·  brief_result
    """

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, verbose: bool = False):
        self._verbose = verbose
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._pending_tool: str | None = None  # tool name waiting for its result

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
        """Display tool call + result pairs (verbose) or suppress (spinner)."""
        if not _IS_TTY:
            return

        typ = str(event.get("type") or event.get("event") or "").lower()

        # Tool call — record name, print in verbose mode
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
                    sys.stdout.write(f"\r\033[K  {_dim('›')}  {_cyan(name):<32}")
                    sys.stdout.flush()
            return

        # Tool result — print summary alongside the pending tool name
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
        # Re-print banner so provider hint appears now that setup is done
        if _IS_TTY:
            print()
            print(_make_banner())
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
        if _IS_TTY:
            print()
            print(_make_banner())
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

def _read_block(first_turn: bool = True) -> list[str]:
    """
    Collect lines until empty line (double-Enter) or Ctrl+D.
    Pipe mode: read all of stdin.

    Shows submission hint on the very first turn so users know the UX.
    """
    if not _IS_INPUT_TTY:
        return sys.stdin.read().splitlines()

    lines: list[str] = []
    prompt_first = "\033[1;36m>\033[0m " if _IS_TTY else "> "
    prompt_cont  = "\033[2m…\033[0m " if _IS_TTY else "  "

    # Hint on first-ever turn — echoed once then never again
    if first_turn and _IS_TTY:
        sys.stdout.write(_dim("  (empty line or Ctrl+D to submit)\n"))

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
    domain = (session.domain or "not classified yet").replace("_", " ")
    print(f"  {_bold('Domain')}    {domain}")
    user_turns = len([t for t in session.turns if t.role == "user"])
    ev_blocks  = len(session.evidence_blocks)
    print(f"  {_bold('Turns')}     {user_turns}  {_dim(f'·  {ev_blocks} evidence block(s)')}")
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

def _print_result(result, *, elapsed: float | None = None, session_id: str | None = None) -> None:
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

    # Footer: timing + session ID (Pi/Ampcode response footer pattern)
    footer_parts: list[str] = []
    if elapsed is not None:
        footer_parts.append(f"{elapsed:.0f}s")
    if session_id:
        footer_parts.append(f"session {session_id}")
    if footer_parts and _IS_TTY:
        print(_dim("  " + "  ·  ".join(footer_parts)))
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
        if _IS_TTY:
            print(_make_banner())
        if session.turns:
            domain_str = (session.domain or "unknown").replace("_", " ")
            user_turns = len([t for t in session.turns if t.role == "user"])
            last = next((t for t in reversed(session.turns) if t.role == "user"), None)
            print(
                f"  {_dim('Resumed')}  {_bold(session.session_id)}  "
                f"{_dim(f'·  {domain_str}  ·  {user_turns} turn(s)')}"
            )
            if last:
                preview = last.content[:80].replace("\n", " ")
                print(f"  {_dim('Last:')}  {preview}")
            print()
        else:
            print(f"  {_dim('Session')} {_bold(session.session_id)} {_dim('is empty — start fresh.')}")
            print()
    else:
        session = DiagnosticSession()
        if _IS_TTY:
            print(_make_banner())
            # Session greeting — grounds user in context (like Pi/Ampcode)
            print(f"  {_dim('New session')}  {_bold(session.session_id)}")
            print()

    # ── First-run guard (TTY interactive only) ────────────────────────
    if _IS_TTY and _IS_INPUT_TTY and not initial_text:
        pi_ok, key_ok = _check_pi_ready()
        if not pi_ok:
            _run_first_time_setup()
        elif not key_ok:
            _run_api_key_setup()

    _first_turn = True  # tracks whether to show the submission hint

    def _process(text: str) -> bool:
        """
        Run one diagnostic turn against Pi.
        Returns True on success, False on failure (allows retry).
        """
        session.add_evidence(text)
        session.add_turn("user", text)

        from signatures import auto_detect
        detections = auto_detect(session.accumulated_evidence)
        domain = detections[0]["domain"] if detections else "unknown"
        conf   = detections[0]["confidence"] if detections else 0.0
        session.domain = domain

        user_turns = [t for t in session.turns if t.role == "user"]
        turn_n = len(user_turns)

        if _IS_TTY:
            turn_hint = f"  {_dim(f'·  Turn {turn_n}')}" if turn_n > 1 else ""
            print(
                f"  {_dim('Domain:')}  {_bold(domain.replace('_', ' '))}  "
                f"{_dim(f'({conf:.0%})')}{turn_hint}"
            )

        # On turn 1 with no log-like content, show evidence hint but still proceed
        # (Pi can ask for more details; we don't block the user)
        if not session.has_log_content(session.accumulated_evidence) and turn_n == 1 and not initial_text:
            hint = _evidence_hint(domain)
            print(
                f"\n  {_dim('No log content detected. Describe your issue and paste error output.')}"
                f"{hint}"
            )
            # Don't block — if user provided a meaningful description, try anyway
            if len(text.split()) < 8:
                # Too brief; wait for more context
                return True

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
            print(f"\n  {_dim('Cancelled.')}\n")
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

        return False  # signal failure to caller for retry prompt

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
            lines = _read_block(first_turn=_first_turn)
            _first_turn = False
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
            # Assign new session ID and show it
            import uuid
            session.session_id = str(uuid.uuid4())[:8]
            _first_turn = True
            print(f"\n  {_dim('Session cleared.')}  {_dim('New session')} {_bold(session.session_id)}\n")

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
            if _IS_TTY:
                print()
                print(_make_banner())

        # /verbose
        elif first == "/verbose":
            session.verbose = not session.verbose
            state = _green("on  — tool calls and results will be shown") if session.verbose else _dim("off")
            print(f"\n  Verbose: {state}\n")

        else:
            # Regular input — expand file refs and diagnose
            text, file_errors = _expand_file_refs(text)
            for err in file_errors:
                print(err)
            try:
                ok = _process(text)
                if not ok and _IS_TTY and _IS_INPUT_TTY:
                    # Offer retry on failure
                    try:
                        ans = input(f"  {_dim('Retry? [Y/n]')} ").strip().lower()
                        if ans in ("", "y", "yes"):
                            # Re-process with same accumulated evidence
                            # (already added to session; run Pi again)
                            with tempfile.NamedTemporaryFile(
                                mode="w", suffix=".txt", prefix="storageops-retry-",
                                delete=False, encoding="utf-8",
                            ) as tmp:
                                tmp.write(session.accumulated_evidence)
                                retry_path = tmp.name
                            progress = _LiveProgress(verbose=session.verbose)
                            t_start = time.monotonic()
                            options = AgentRunOptions(
                                runtime="pi",
                                stream=False,
                                max_turns=10,
                                timeout_seconds=600,
                                pi_command=get_pi_command(),
                                event_callback=progress.on_event,
                            )
                            try:
                                with progress:
                                    from storageops.runtime import PiRpcRuntime as _Rpc
                                    result = _Rpc(options).run(retry_path)
                            finally:
                                try:
                                    Path(retry_path).unlink()
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
                    except (EOFError, KeyboardInterrupt):
                        print()
            except KeyboardInterrupt:
                print(f"\n  {_dim('Interrupted. Type /exit to quit or continue.')}\n")
