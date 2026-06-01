"""Interactive REPL — Pi Coding Agent-style S3 diagnostic interface."""
from __future__ import annotations

import re
import sys
import select as _select
import tempfile
import time
from pathlib import Path
from typing import Any

from storageops.session import DiagnosticSession

_IS_TTY       = sys.stdout.isatty()
_IS_INPUT_TTY = sys.stdin.isatty()

# ── ANSI helpers ──────────────────────────────────────────────────────

# Look-up table: colour name → ansi code
_CODES = {
    "reset": 0, "bold": 1, "dim": 2, "italic": 3,
    "green": 32, "yellow": 33, "red": 31, "cyan": 36,
    "magenta": 35, "blue": 34,
}

def _c(text: str, *args: str) -> str:
    """Apply ANSI codes. _c('text', 'bold', 'cyan') → bold cyan text."""
    if not _IS_TTY:
        return text
    codes = [str(_CODES.get(a, a)) for a in args]
    return "\033[" + ";".join(codes) + "m" + text + "\033[0m"

def _bold(t: str) -> str:   return _c(t, "bold")
def _dim(t: str) -> str:    return _c(t, "dim")
def _green(t: str) -> str:  return _c(t, "green")
def _yellow(t: str) -> str: return _c(t, "yellow")
def _red(t: str) -> str:    return _c(t, "red")
def _cyan(t: str) -> str:   return _c(t, "cyan")

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
    "/setup":   "Re-run setup (API key, Pi install)",
    "/verbose": "Toggle verbose mode (show tool calls)",
    "/exit":    "Exit StorageOps",
}

_SLASH_CMD_GROUPS = [
    ("Session",       ["/resume", "/clear", "/status"]),
    ("Configuration", ["/config", "/setup", "/doctor", "/update"]),
    ("Memory",        ["/memory"]),
    ("Other",         ["/verbose", "/help", "/exit"]),
]


# ── Banner ────────────────────────────────────────────────────────────

def _make_banner() -> str:
    provider_str = ""
    try:
        from storageops.config import get_provider, get_api_key
        if get_api_key():
            provider_str = f"  {_c(get_provider(), 'cyan')}"
        else:
            provider_str = f"  {_c('no api key — /setup', 'yellow')}"
    except Exception:
        pass
    lines = [
        _c("StorageOps", "bold"),
        f"{provider_str}",
        "",
        _c("Describe your S3 issue or paste a log file.", "dim"),
        _c("Use @filename  to attach files.  /help for commands.", "dim"),
    ]
    return "\n".join(lines)


def _make_prompt(session_id: str) -> str:
    """Build the input prompt: `  › ` (clean, pi-style)."""
    return f"  {_c('›', 'cyan')}  " if _IS_TTY else "> "


# ── Live streaming progress (tool calls + report streaming) ───────────

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


class _StreamDisplay:
    """
    Pi-style streaming progress during diagnosis.

    Shows tool calls in real-time, streams the final report as it's written,
    and dims the thinking phase to a single indicator line.

      ▶ Thinking…
         Scanning evidence for error signatures…
      ⏺ scan_secrets  ✓ 0 secrets
      ⏺ triage  ✓ performance_throughput 25%
      ⏺ analyze  ✓ 2 findings

      ────────────────────────────────────────────────────
        prefix hotspot throttling  HIGH  75%
      ────────────────────────────────────────────────────

      (report body streamed in real-time)
    """

    def __init__(self):
        self._thinking_lines = 0
        self._thinking_header_shown = False
        self._report_started = False
        self._current_tool: str | None = None
        self._first_report_line = True
        self._yaml_buffer: list[str] = []
        self._yaml_collecting = False
        self._header_printed = False

    def on_event(self, event: dict[str, Any]) -> None:
        if not _IS_TTY:
            return

        typ = str(event.get("type") or event.get("event") or "").lower()

        # ── Text streaming ──────────────────────────────────────────
        if typ == "message_update":
            ae = event.get("assistantMessageEvent", {})
            if not isinstance(ae, dict) or ae.get("type") != "text_delta":
                return
            delta = ae.get("delta", "")
            if not delta:
                return

            # Detect report start: YAML frontmatter `---` after a blank or on new line
            if not self._report_started and delta.strip().startswith("---"):
                # End thinking block
                if self._thinking_lines > 0 and self._thinking_header_shown:
                    print()  # newline after thinking
                print()  # blank before report header
                self._report_started = True
                self._yaml_collecting = True
                self._yaml_buffer = []
                return

            if self._yaml_collecting:
                self._yaml_buffer.append(delta)
                # End of YAML frontmatter
                if delta.strip() == "---":
                    self._yaml_collecting = False
                    self._print_yaml_header()
                return

            if self._report_started:
                # Stream report body
                print(delta, end="", flush=True)
                return

            # Thinking phase: summarise to 1-2 lines only
            if self._thinking_lines == 0:
                print(f"\n  {_c('▶', 'cyan')}  {_c('Thinking…', 'dim')}")
                self._thinking_header_shown = True
            if self._thinking_lines < 2:
                preview = delta.strip()[:100]
                if preview:
                    print(f"     {_c(preview, 'dim')}")
            self._thinking_lines += 1
            return

        # ── Tool calls ──────────────────────────────────────────────
        if typ in ("tool_use", "tool_call", "function_call"):
            name = (
                event.get("name")
                or event.get("tool_name")
                or (event.get("function") or {}).get("name")
                or (event.get("tool") or {}).get("name")
            )
            if not name:
                return
            # End thinking line if we were in thinking phase
            if self._thinking_lines > 0 and self._thinking_header_shown:
                print()
            self._current_tool = name
            # Show tool name with indent, pad to align results
            print(f"  {_c('⏺', 'cyan')}  {_c(name, 'cyan')}", end="", flush=True)
            return

        # ── Tool results ────────────────────────────────────────────
        if typ in ("tool_result", "function_result"):
            if self._current_tool:
                summary = _summarize_tool_result(event)
                mark = _c("✓", "green") if summary and "error" not in summary.lower() else _c("✗", "red")
                detail = summary if summary else "ok"
                print(f"  {mark} {_c(detail, 'dim')}")
            self._current_tool = None
            return

        # ── Agent end ───────────────────────────────────────────────
        if typ == "agent_end":
            if self._thinking_lines > 0 and self._thinking_header_shown:
                print()
            return

    def _print_yaml_header(self) -> None:
        """Parse collected YAML frontmatter and print a formatted header."""
        yaml_text = "".join(self._yaml_buffer)
        fm_rc = re.search(r'^root_cause_type:\s*(\S+)', yaml_text, re.MULTILINE)
        fm_conf = re.search(r'^confidence:\s*([\d.]+)', yaml_text, re.MULTILINE)
        fm_sev = re.search(r'^severity:\s*(\S+)', yaml_text, re.MULTILINE)

        sev_str = fm_sev.group(1).upper() if fm_sev else ""
        conf_str = f"{float(fm_conf.group(1)):.0%}" if fm_conf else ""
        rc_str = fm_rc.group(1).replace("_", " ") if fm_rc else "diagnosis"

        sev_color = (
            "red"    if sev_str in ("HIGH", "CRITICAL") else
            "yellow" if sev_str == "MEDIUM" else
            "dim"
        )

        print(_hr(56))
        print(f"  {_c(rc_str, 'bold')}  {_c(sev_str, sev_color)}  {_c(conf_str, 'dim')}")
        print(_hr(56))
        print()
        self._header_printed = True


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

def _read_input(prompt: str | None = None) -> str | None:
    """
    Read one logical user input.

    Interactive: Enter submits.  Line ending in backslash continues to next line.
    Pipe mode: read all of stdin.
    Returns None on EOF/Ctrl+D (exit signal).
    """
    if not _IS_INPUT_TTY:
        data = sys.stdin.read()
        return data if data.strip() else None

    _prompt = prompt if prompt is not None else (f"{_c('>', 'cyan')} " if _IS_TTY else "> ")

    lines: list[str] = []
    first = True
    while True:
        p = _prompt if first else f"  {_c('…', 'dim')}  "
        first = False
        try:
            line = input(p)
        except EOFError:
            if not lines:
                return None
            break
        # Check for paste buffering
        extra: list[str] = []
        try:
            while True:
                r, _, _ = _select.select([sys.stdin], [], [], 0)
                if not r:
                    break
                nl = sys.stdin.readline()
                if not nl:
                    break
                extra.append(nl.rstrip("\n"))
        except Exception:
            pass
        if extra:
            lines.append(line)
            lines.extend(extra)
            break
        # Multi-line continuation: line ending in \
        if line.rstrip().endswith("\\"):
            lines.append(line.rstrip()[:-1].rstrip())
            continue
        lines.append(line)
        break

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
    for group_name, cmds in _SLASH_CMD_GROUPS:
        print(f"  {_dim(group_name)}")
        for cmd in cmds:
            desc = _SLASH_CMD_HELP.get(cmd, "")
            print(f"    {_cyan(cmd):<18}  {_dim(desc)}")
        print()
    print(f"  {_dim('Tip: use @/path/to/file to include a file in your message')}")
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
    print(f"  {'Domain':<30} {'Root cause':<36} {'Date'}")
    print(f"  {_dim('─' * 78)}")
    for c in cases:
        ts     = (c.get("timestamp") or "")[:10]
        domain = (c.get("domain") or "unknown").replace("_", " ")[:28]
        rc     = (c.get("root_cause_type") or "")[:34]
        print(f"  {_cyan(domain):<30} {_dim(rc):<36} {_dim(ts)}")
    print()
    print(f"  {_dim('/memory search <query> to search by keyword')}\n")


# ── Response display ──────────────────────────────────────────────────

def _print_result(result, *, elapsed: float | None = None, session_id: str | None = None) -> None:
    """Show footer after a streamed diagnosis: elapsed time, session id, or error."""
    if not result.ok:
        err = result.error or "Unknown error"
        _pi_missing = any(kw in err.lower() for kw in (
            "not found", "no such file", "filenotfounderror",
            "command not found", "permission denied", "pi: not found",
        ))
        if _pi_missing:
            print(f"\n  {_c('Pi Agent not found.', 'red')}")
            print(f"  {_c('Run', 'dim')} {_c('storageops setup', 'bold')} {_c('to install Pi, or type', 'dim')} {_c('/setup', 'bold')} {_c('here.', 'dim')}")
        else:
            print(f"\n  {_c('✗', 'red')}  Diagnosis failed: {_c(err, 'dim')}")
            print(f"  {_c('/doctor to check installation  ·  /setup to reconfigure', 'dim')}")
        print()
        return

    # Report was already streamed in real-time.
    # Show footer: elapsed time + session id.
    footer_parts: list[str] = []
    if elapsed is not None:
        footer_parts.append(f"{elapsed:.0f}s")
    if session_id:
        footer_parts.append(f"session {session_id}")
    if footer_parts and _IS_TTY:
        print()
        print(_c("  " + "  ·  ".join(footer_parts), "dim"))
        print()


# ── Turn runner ───────────────────────────────────────────────────────

def _run_turn(text: str, session: DiagnosticSession) -> bool:
    """Send one turn to Pi. Streams progress and report in real-time."""
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

    display = _StreamDisplay()
    t_start = time.monotonic()

    options = AgentRunOptions(
        runtime="pi",
        stream=True,   # enable real-time Pi output
        max_turns=10,
        timeout_seconds=600,
        verbose=False,  # verbose handled by _StreamDisplay now
        pi_command=get_pi_command(),
        event_callback=display.on_event,
    )

    try:
        result = PiRpcRuntime(options).run(tmp_path)
    except KeyboardInterrupt:
        print(f"\n  {_c('Interrupted.', 'dim')}\n")
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
            print(f"  {_dim('Session')}  {_bold(session.session_id)}  {_dim('·  new')}")
            print()

    # First-run: if no API key, configure inline (like Claude Code / Pi)
    if _IS_TTY and _IS_INPUT_TTY and not initial_text:
        from storageops.config import get_api_key
        if not get_api_key():
            _first_run_configure()

    # One-shot mode (pipe or direct argument)
    if initial_text:
        if not _IS_INPUT_TTY and _IS_TTY:
            lines = initial_text.count("\n") + 1
            print(f"  {_green('✓')}  {_dim(f'Received {lines} line(s) from stdin')}")
        expanded, errs = _expand_file_refs(initial_text)
        for e in errs:
            print(e)
        _run_turn(expanded, session)
        return

    # Interactive loop
    _empty_hint_shown = False
    while True:
        try:
            text = _read_input(_make_prompt(session.session_id))
        except KeyboardInterrupt:
            print(f"\n  {_dim('/exit to quit')}\n")
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
            if not _empty_hint_shown and _IS_TTY:
                print(f"  {_c('Describe your S3 issue, paste a log, or type / for commands.', 'dim')}")
                print(f"  {_c('Use backslash at end of line for multi-line input.', 'dim')}")
                _empty_hint_shown = True
            continue
        _empty_hint_shown = False

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
            _empty_hint_shown = False
            print(f"\n  {_green('✓')}  New session  {_bold(session.session_id)}\n")

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
            state = _c("on", "green") if session.verbose else _c("off", "dim")
            print(f"\n  Verbose: {state}  ({_c('shows full thinking text', 'dim')})\n")

        else:
            expanded, file_errors = _expand_file_refs(text)
            for err in file_errors:
                print(err)
            try:
                _run_turn(expanded, session)
            except KeyboardInterrupt:
                print(f"\n  {_yellow('⊘')}  Stopped.  {_dim('Continue asking or type /exit to quit.')}\n")
