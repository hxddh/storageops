"""Interactive REPL — natural-language S3 diagnostic agent interface."""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
import threading
from pathlib import Path

from storageops.session import DiagnosticSession

_BANNER = """\
\033[1mStorageOps\033[0m  S3 Diagnostic Agent
Describe your issue or paste error logs. Use \033[2m@file.log\033[0m to reference a file.
\033[2m/help for commands · Ctrl+C or /exit to quit\033[0m
"""

_HELP = """
Commands:
  /help      This message
  /clear     Clear session and start fresh
  /doctor    Environment health check
  /setup     Re-run setup wizard
  /verbose   Toggle verbose mode
  /exit      Exit

Tips:
  • Paste log output directly — StorageOps detects it automatically
  • Reference a file:  @/path/to/error.log
  • Empty line submits a multi-line block
"""

_IS_TTY = sys.stdout.isatty()


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


# ── Spinner ───────────────────────────────────────────────────────────

class _Spinner:
    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, label: str = "Analyzing"):
        self._label = label
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def __enter__(self):
        if _IS_TTY:
            self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if _IS_TTY and self._thread.is_alive():
            self._thread.join(timeout=1)
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._FRAMES[i % len(self._FRAMES)]
            sys.stdout.write(f"\r  {_cyan(frame)}  {_dim(self._label + '...')}")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1


# ── Input reading ─────────────────────────────────────────────────────

def _init_readline() -> None:
    try:
        import readline  # noqa: F401
    except ImportError:
        pass


def _read_block() -> list[str]:
    """Read one block of input from the user.

    In TTY mode: collect lines until an empty line (double-Enter) or Ctrl+D.
    In pipe mode: read all of stdin at once.
    """
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


# ── Response display ──────────────────────────────────────────────────

def _print_result(result) -> None:
    """Display a Pi diagnostic result (AgentRunResult)."""
    if not result.ok:
        print()
        print(f"  {_red('Diagnosis failed')}")
        print(f"  {_dim(result.error or 'Unknown error')}")
        print()
        return

    report = result.report_markdown.strip()
    if not report:
        print(f"  {_yellow('No report generated.')}")
        return

    # Extract frontmatter for summary line
    fm_cat  = re.search(r'^category:\s*(\S+)',       report, re.MULTILINE)
    fm_rc   = re.search(r'^root_cause_type:\s*(\S+)', report, re.MULTILINE)
    fm_conf = re.search(r'^confidence:\s*([\d.]+)',   report, re.MULTILINE)
    fm_sev  = re.search(r'^severity:\s*(\S+)',        report, re.MULTILINE)

    print()
    print(_hr(56))
    if fm_cat and fm_rc:
        sev_str = fm_sev.group(1).upper() if fm_sev else ""
        conf_str = f"{float(fm_conf.group(1)):.0%}" if fm_conf else ""
        sev_color = _red if sev_str in ("HIGH", "CRITICAL") else _yellow if sev_str == "MEDIUM" else _dim
        print(
            f"  {_bold(fm_rc.group(1).replace('_', ' '))}  "
            f"{sev_color(sev_str)}  {_dim(conf_str)}"
        )
    print(_hr(56))
    print()

    # Strip YAML frontmatter before printing body
    body = re.sub(r'^---\n.*?\n---\n?', '', report, flags=re.DOTALL).strip()
    print(body)
    print()


# ── Main REPL loop ────────────────────────────────────────────────────

def run_repl(initial_text: str | None = None, resume_session: str | None = None) -> None:
    """Start the interactive diagnostic REPL."""
    from storageops.runtime import AgentRunOptions, PiRpcRuntime

    _init_readline()

    if resume_session:
        session = DiagnosticSession.load(resume_session)
        if session is None:
            print(f"  {_red('✗')}  Session not found: {resume_session}")
            session = DiagnosticSession()
        else:
            if _IS_TTY:
                print(_BANNER)
            print(f"  {_dim('Resumed session')}  {_bold(session.session_id)}  "
                  f"{_dim(session.domain or 'unknown domain')}")
            if session.turns:
                last = next((t for t in reversed(session.turns) if t.role == "user"), None)
                if last:
                    print(f"  {_dim('Last:')}  {last.content[:80]}")
            print()
    else:
        session = DiagnosticSession()
        if _IS_TTY:
            print(_BANNER)

    def _process(text: str) -> None:
        """Run one diagnostic turn."""
        session.add_evidence(text)
        session.add_turn("user", text)

        # Domain detection
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

        # If no real log content yet, ask for evidence
        if not session.has_log_content(session.accumulated_evidence) and not initial_text:
            hint = _evidence_hint(domain)
            print(f"\n  {_dim('Paste your error log or command output below.')}{hint}")
            return

        # Write accumulated evidence to temp file and run Pi
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="storageops-session-",
            delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(session.accumulated_evidence)
            tmp_path = tmp.name

        options = AgentRunOptions(
            runtime="pi",
            stream=_IS_TTY,
            max_turns=10,
            timeout_seconds=600,
            verbose=session.verbose,
        )

        try:
            with _Spinner("Analyzing"):
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

    # One-shot mode (piped input or direct argument)
    if initial_text:
        expanded, errs = _expand_file_refs(initial_text)
        for e in errs:
            print(e)
        _process(expanded)
        return

    # Interactive loop
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

        # Slash commands
        first = text.split()[0].lower()
        if first in ("/exit", "/quit") or text.lower() in ("exit", "quit"):
            print("Goodbye.")
            break
        elif first == "/help":
            print(_HELP)
            continue
        elif first == "/clear":
            session.reset()
            print(_dim("  Session cleared.\n"))
            continue
        elif first == "/doctor":
            import argparse
            from storageops.cli import cmd_doctor
            cmd_doctor(argparse.Namespace())
            continue
        elif first == "/setup":
            import argparse
            from storageops.cli import cmd_setup
            cmd_setup(argparse.Namespace(pi_command="pi"))
            continue
        elif first == "/verbose":
            session.verbose = not session.verbose
            print(_dim(f"  Verbose: {'on' if session.verbose else 'off'}\n"))
            continue

        # Expand @file references
        text, file_errors = _expand_file_refs(text)
        for err in file_errors:
            print(err)

        try:
            _process(text)
        except KeyboardInterrupt:
            print(f"\n  {_dim('Interrupted. Type /exit to quit or continue.')}\n")
