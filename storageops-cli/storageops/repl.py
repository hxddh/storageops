"""Interactive REPL — Pi Coding Agent-style S3 diagnostic interface."""
from __future__ import annotations

import os
import re
import sys
import select as _select
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from storageops.session import DiagnosticSession

# ── History file path ────────────────────────────────────────────────

def _history_file() -> Path:
    """Return ~/.storageops/history."""
    from storageops.config import get_workdir
    return get_workdir() / "history"

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
    "/help", "/history", "/resume", "/clear", "/status",
    "/config", "/memory", "/update",
    "/doctor", "/setup", "/verbose", "/editor", "/view", "/exit",
]

_SLASH_CMD_HELP = {
    "/help":    "Show this command list",
    "/history": "Show command history  (/history <N> for last N)",
    "/resume":  "Load a past session",
    "/clear":   "Clear context and start a fresh session",
    "/status":  "Show session info and configuration",
    "/config":  "View or change configuration  (/config set <key> <val>)",
    "/memory":  "Browse past cases  (/memory search <query>)",
    "/editor":  "Open $EDITOR to write a long prompt or paste a large log",
    "/view":    "Open the last report in a pager (less) for full-screen browsing",
    "/update":  "Download latest Pi binary and reinstall skills",
    "/doctor":  "Run environment health check",
    "/setup":   "Re-run setup (API key, Pi install)",
    "/verbose": "Toggle verbose mode (show tool calls)",
    "/exit":    "Exit StorageOps",
}

_SLASH_CMD_GROUPS = [
    ("Session",       ["/resume", "/clear", "/editor", "/view", "/status", "/history"]),
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
        _c("@file to attach   $ cmd to run   /editor for long prompts   /help for commands", "dim"),
    ]
    return "\n".join(lines)


def _make_prompt(session_id: str) -> str:
    """Build the input prompt: `  › ` (clean, pi-style)."""
    return f"  {_c('›', 'cyan')}  " if _IS_TTY else "> "


# ── Live streaming progress (tool calls + report streaming) ───────────

def _summarize_tool_result(event: dict[str, Any]) -> str:
    """Extract a brief human-readable summary from a Pi tool_execution_end event."""
    # Pi format: {type: "tool_execution_end", result: {content: [{type: "text", text: "..."}]}}
    result = event.get("result", {})
    if isinstance(result, dict):
        content_list = result.get("content", [])
        if content_list and isinstance(content_list[0], dict):
            text = content_list[0].get("text", "")
            if isinstance(text, str):
                try:
                    data = __import__("json").loads(text)
                    return _summarize_structured(data)
                except Exception:
                    return text[:60].replace("\n", " ")
        # Check details for structured data
        details = result.get("details", {})
        if details:
            return _summarize_structured(details)
        return ""
    # Legacy format: direct content/result/output
    content = event.get("content") or event.get("output") or {}
    if isinstance(content, str):
        try:
            data = __import__("json").loads(content)
            return _summarize_structured(data)
        except Exception:
            return content[:60].replace("\n", " ")
    if isinstance(content, dict):
        return _summarize_structured(content)
    return ""


def _summarize_structured(data: dict) -> str:
    """Extract key fields from structured tool output."""
    snippets: list[str] = []
    for key in ("records", "transfers", "errors", "requests", "signals", "findings", "count"):
        v = data.get(key)
        if isinstance(v, list) and v:
            snippets.append(f"{len(v)} {key}")
        elif isinstance(v, int) and v:
            snippets.append(f"{v} {key}")
    for key in ("root_cause_type", "root_cause", "domain", "bottleneck", "primary_domain"):
        v = data.get(key)
        if isinstance(v, str) and v:
            snippets.append(v.replace("_", " ")[:30])
            break
    for key in ("confidence",):
        v = data.get(key)
        if isinstance(v, (int, float)):
            snippets.append(f"{v:.0%}")
    for key in ("ok", "valid"):
        v = data.get(key)
        if isinstance(v, bool):
            snippets.append("ok" if v else "failed")
            break
    return "  ".join(snippets[:3])


# ── Syntax highlighting (optional, uses pygments) ────────────────────

_HIGHLIGHT_AVAILABLE = False

def _init_highlighting() -> bool:
    """Check if pygments is available for syntax highlighting."""
    global _HIGHLIGHT_AVAILABLE
    try:
        __import__("pygments")
        _HIGHLIGHT_AVAILABLE = True
    except ImportError:
        _HIGHLIGHT_AVAILABLE = False
    return _HIGHLIGHT_AVAILABLE


def _highlight_text(text: str, lexer_name: str) -> str:
    """Apply pygments syntax highlighting. Returns plain text if unavailable."""
    if not _HIGHLIGHT_AVAILABLE or not _IS_TTY:
        return text
    try:
        from pygments import highlight
        from pygments.lexers import get_lexer_by_name
        from pygments.formatters import Terminal256Formatter
        lexer = get_lexer_by_name(lexer_name, stripall=True)
        return highlight(text, lexer, Terminal256Formatter(style="monokai"))
    except Exception:
        return text


def _highlight_report_sections(text: str) -> str:
    """
    Highlight YAML blocks, code fences, and numbered lists in a report.
    Returns the plain text (highlighting only applied during TTY streaming).
    """
    if not _IS_TTY or not _HIGHLIGHT_AVAILABLE:
        return text
    try:
        from pygments import highlight
        from pygments.lexers import YamlLexer, JsonLexer, BashLexer, MarkdownLexer
        from pygments.formatters import Terminal256Formatter

        result: list[str] = []
        in_yaml = False
        in_code = False
        code_lang = ""
        yaml_lines: list[str] = []
        code_lines: list[str] = []

        fm = Terminal256Formatter(style="monokai")

        for line in text.split("\n"):
            # YAML frontmatter
            if not in_yaml and not in_code and line.strip() == "---":
                in_yaml = True
                yaml_lines = [line]
                continue
            if in_yaml:
                yaml_lines.append(line)
                if line.strip() == "---" and len(yaml_lines) > 1:
                    # Flush YAML block
                    yaml_text = "\n".join(yaml_lines)
                    try:
                        highlighted = highlight(yaml_text, YamlLexer(), fm)
                        result.append(highlighted.rstrip())
                    except Exception:
                        result.append(yaml_text.rstrip())
                    yaml_lines = []
                    in_yaml = False
                continue

            # Code fence
            fence_match = re.match(r"^```(\w*)", line.strip())
            if fence_match and not in_code:
                in_code = True
                code_lang = fence_match.group(1) or ""
                code_lines = [line]
                continue
            if in_code:
                code_lines.append(line)
                if line.strip() == "```":
                    # Flush code block
                    code_text = "\n".join(code_lines)
                    lexer_map = {
                        "yaml": YamlLexer, "yml": YamlLexer,
                        "json": JsonLexer, "bash": BashLexer, "sh": BashLexer,
                        "shell": BashLexer,
                    }
                    lexer_cls = lexer_map.get(code_lang, MarkdownLexer)
                    try:
                        highlighted = highlight(code_text, lexer_cls(), fm)
                        result.append(highlighted.rstrip())
                    except Exception:
                        result.append(code_text.rstrip())
                    code_lines = []
                    in_code = False
                continue

            result.append(line)

        # Close unclosed blocks
        if yaml_lines:
            result.extend(yaml_lines)
        if code_lines:
            result.extend(code_lines)

        return "\n".join(result)
    except Exception:
        return text


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
        self._tool_count = 0
        self._t_start: float | None = None

    def on_event(self, event: dict[str, Any]) -> None:
        if not _IS_TTY:
            return

        typ = str(event.get("type") or "").lower()

        # ── Text streaming (thinking + report) ─────────────────────
        if typ == "message_update":
            ae = event.get("assistantMessageEvent", {})
            if not isinstance(ae, dict):
                return
            ae_type = ae.get("type", "")
            # Handle text_start (first chunk) and text_delta (incremental)
            if ae_type not in ("text_delta", "text_start"):
                return
            delta = ae.get("delta", "")
            # text_start embeds text in partial.content[0].text
            if ae_type == "text_start" and not delta:
                partial = ae.get("partial", {})
                content = partial.get("content", [])
                if content and isinstance(content[0], dict):
                    delta = content[0].get("text", "")
            if not delta:
                return

            # Detect report start: YAML frontmatter `---`
            if not self._report_started and "---" in delta:
                # Find YAML start position within delta
                yaml_idx = delta.find("---")
                # Print anything before YAML as thinking
                if yaml_idx > 0:
                    thinking_part = delta[:yaml_idx]
                    if self._thinking_lines == 0:
                        print(f"\n  {_c('▶', 'cyan')}  {_c('Thinking…', 'dim')}")
                        self._thinking_header_shown = True
                    if self._thinking_lines < 2:
                        preview = thinking_part.strip()[:100]
                        if preview:
                            print(f"     {_c(preview, 'dim')}")
                    self._thinking_lines += 1
                # Enter report phase
                if self._thinking_lines > 0 and self._thinking_header_shown:
                    print()
                print()
                self._report_started = True
                self._yaml_collecting = True
                self._yaml_buffer = []
                # Feed YAML bytes starting from ---
                after_yaml = delta[yaml_idx:]
                self._yaml_buffer.append(after_yaml)
                if after_yaml.strip() == "---":
                    self._yaml_collecting = False
                    self._print_yaml_header()
                return

            if self._yaml_collecting:
                self._yaml_buffer.append(delta)
                combined = "".join(self._yaml_buffer)
                # End of YAML: second ---
                if "---" in combined[4:]:  # after first ---
                    self._yaml_collecting = False
                    self._print_yaml_header()
                return

            if self._report_started:
                # Stream report body
                print(delta, end="", flush=True)
                return

            # Thinking phase: summarise to 1-2 lines
            if self._thinking_lines == 0:
                print(f"\n  {_c('▶', 'cyan')}  {_c('Thinking…', 'dim')}")
                self._thinking_header_shown = True
            if self._thinking_lines < 2:
                preview = delta.strip()[:100]
                if preview:
                    print(f"     {_c(preview, 'dim')}")
            self._thinking_lines += 1
            return

        # ── Tool calls (Pi uses tool_execution_start/tool_execution_end) ──
        if typ == "tool_execution_start":
            name = event.get("toolName", "")
            if not name:
                return
            if self._thinking_lines > 0 and self._thinking_header_shown:
                print()
            self._current_tool = name
            self._tool_count += 1
            elapsed = f"{time.monotonic() - self._t_start:.0f}s" if self._t_start else ""
            print(f"  {_c('⏺', 'cyan')}  {_c(name, 'cyan')}", end="", flush=True)
            return

        # ── Tool results ────────────────────────────────────────────
        if typ == "tool_execution_end":
            if self._current_tool:
                is_error = bool(event.get("isError"))
                result = event.get("result", {})
                summary = _summarize_tool_result(event)
                if is_error:
                    mark = _c("✗", "red")
                    detail = summary or "error"
                else:
                    mark = _c("✓", "green")
                    detail = summary or "ok"
                elapsed = f"{time.monotonic() - self._t_start:.0f}s" if self._t_start else ""
                progress = f" ({elapsed})" if elapsed else ""
                print(f"  {mark} {_c(detail, 'dim')}{_c(progress, 'dim')}")
            self._current_tool = None
            return

        # ── Agent end ───────────────────────────────────────────────
        if typ == "agent_end":
            if self._thinking_lines > 0 and self._thinking_header_shown:
                print()
            return

        # ── Turn start (track elapsed) ──────────────────────────────
        if typ == "turn_start" and self._t_start is None:
            self._t_start = time.monotonic()
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


# ── Readline history + tab completion ───────────────────────────────

# Track history in memory for /history command (readline persists to file)
_HISTORY_LINES: list[str] = []
_HISTORY_MAX = 2000


def _append_history(text: str) -> None:
    """Record a line to in-memory history (readline already saves to file)."""
    if text and text.strip() and not text.strip().startswith("/"):
        if not _HISTORY_LINES or _HISTORY_LINES[-1] != text:
            _HISTORY_LINES.append(text)
            if len(_HISTORY_LINES) > _HISTORY_MAX:
                _HISTORY_LINES[:] = _HISTORY_LINES[-_HISTORY_MAX:]


def _show_history(n: int = 20) -> None:
    """Print the last n history entries."""
    if not _HISTORY_LINES:
        print(f"\n  {_dim('No history yet.')}\n")
        return
    print()
    entries = _HISTORY_LINES[-n:]
    for i, line in enumerate(entries, max(1, len(_HISTORY_LINES) - n + 1)):
        preview = line[:100].replace("\n", " ")
        print(f"  {_dim(str(i).rjust(4))}  {_dim(preview)}")
    print()


def _init_readline() -> None:
    try:
        import readline
    except ImportError:
        return

    # ── History persistence ──────────────────────────────────────
    hist_file = _history_file()
    hist_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(str(hist_file))
        # Load into in-memory tracker too
        for i in range(readline.get_current_history_length()):
            _HISTORY_LINES.append(readline.get_history_item(i + 1))
    except (OSError, FileNotFoundError):
        pass

    import atexit
    def _save() -> None:
        try:
            readline.set_history_length(_HISTORY_MAX)
            readline.write_history_file(str(hist_file))
        except OSError:
            pass
    atexit.register(_save)

    # ── Tab completion for slash commands ────────────────────────
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
    """Replace @path references with file contents.

    Supports:
      @/absolute/path          — exact path
      @./relative/file.log     — relative path
      @*.log                   — glob: first match in cwd (sorted by mtime)
      @s5cmd*                  — glob prefix: fuzzy-match files in cwd
    Returns (expanded_text, errors).
    """
    errors: list[str] = []

    def _resolve_glob(pattern: str) -> Path | None:
        """Try glob + fuzzy matching for @ references."""
        cwd = Path.cwd()
        if pattern.startswith("/") or pattern.startswith("~"):
            # Absolute path: use Path().glob
            base = Path(pattern).expanduser()
            if base.is_absolute():
                parent = base.parent
                name = base.name
                try:
                    matches = sorted(parent.glob(name), key=lambda p: p.stat().st_mtime, reverse=True)
                except Exception:
                    matches = []
                if matches:
                    return matches[0]
                # Fuzzy prefix on absolute path
                if not any(c in name for c in "*?["):
                    try:
                        fuzzy = sorted(parent.glob(f"{name}*"), key=lambda p: p.stat().st_mtime, reverse=True)
                    except Exception:
                        fuzzy = []
                    if fuzzy:
                        return fuzzy[0]
                return None
        # Relative pattern
        try:
            matches = sorted(cwd.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            matches = []
        if matches:
            return matches[0]
        # Fuzzy prefix: @s5cmd → find s5cmd* files
        if not any(c in pattern for c in "*?["):
            try:
                fuzzy = sorted(cwd.glob(f"{pattern}*"), key=lambda p: p.stat().st_mtime, reverse=True)
            except Exception:
                fuzzy = []
            if fuzzy:
                return fuzzy[0]
        return None

    def _replace(m: re.Match) -> str:
        raw = m.group(1)
        path = Path(raw).expanduser()

        # Exact path exists → use it
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                return f"[{path.name}]\n{content}"
            except OSError as exc:
                errors.append(f"{_red('✗')}  cannot read {path}: {exc}")
                return m.group(0)

        # Glob/fuzzy match in cwd
        resolved = _resolve_glob(raw)
        if resolved:
            try:
                content = resolved.read_text(encoding="utf-8", errors="replace")
                errors.append(f"{_dim('@')}{raw}{_dim(' → ')}{resolved.name}")
                return f"[{resolved.name}]\n{content}"
            except OSError:
                pass

        errors.append(f"{_red('✗')}  file not found: {raw}")
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
    print(f"  {_dim('Tip: $ cmd runs shell commands  ·  @file attaches files  ·  /editor for long input')}")
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


def _handle_editor(session: DiagnosticSession) -> str | None:
    """Open $EDITOR (or vim/nano) for writing a long prompt. Returns text or None."""

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"
    # If vim not available, fall back to nano
    if editor == "vim" and not __import__("shutil").which("vim"):
        editor = "nano"

    hint = (
        "# Write your prompt or paste log content above.\n"
        "# Lines starting with # are ignored.\n"
        "# Save and exit to send.  Exit without saving to cancel.\n"
        "# Use @filename to include files.\n"
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
        print(f"  {_c('✗', 'red')}  Editor not found: {editor}")
        print(f"  {_c('Set $EDITOR or install vim/nano.', 'dim')}")
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        return None

    if result != 0:
        print(f"  {_c('⊘', 'yellow')}  Editor exited with code {result}")
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

    # Strip comment lines
    lines = [l for l in content.splitlines() if not l.strip().startswith("#")]
    text = "\n".join(lines).strip()
    if not text:
        print(f"  {_c('⊘', 'dim')}  Empty prompt (cancelled)")
        return None

    print(f"  {_c('✓', 'green')}  {_c(f'{len(text)} chars from editor', 'dim')}")
    return text


# ── Shell mode handler ────────────────────────────────────────────────

def _handle_shell(text: str, session: DiagnosticSession) -> None:
    """Run a shell command ($ prefix) and add output to session evidence."""

    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("$"):
            continue
        cmd_str = stripped[1:].strip()
        if not cmd_str:
            continue

        print(f"  {_c('$', 'cyan')} {_c(cmd_str, 'dim')}")
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
            print(f"  {_c('  ' + summary, 'dim')}")
            if len(output) > 200:
                print(f"  {_c(f'  … ({len(output)} chars total)', 'dim')}")
            evidence = f"$ {cmd_str}\n{output}"
            session.add_evidence(evidence)
            session.add_turn("user", text)
        except subprocess.TimeoutExpired:
            print(f"  {_c('✗', 'red')}  Command timed out")
        except Exception as exc:
            print(f"  {_c('✗', 'red')}  {exc}")


def _handle_view(session: DiagnosticSession) -> None:
    """Open the last assistant report in a pager for full-screen browsing."""

    last = None
    for t in reversed(session.turns):
        if t.role == "assistant" and t.content:
            last = t.content
            break

    if not last:
        print(f"\n  {_c('No report to view yet.', 'dim')}\n")
        return

    # Strip YAML frontmatter for cleaner viewing
    report = re.sub(r'^---\n.*?\n---\n?', '', last, flags=re.DOTALL).strip()

    # Apply syntax highlighting if available
    if _HIGHLIGHT_AVAILABLE:
        report = _highlight_report_sections(report)

    pager = __import__("os").environ.get("PAGER", "less -R")
    try:
        proc = subprocess.Popen(
            pager.split(), stdin=subprocess.PIPE, text=True,
        )
        proc.communicate(input=report)
    except FileNotFoundError:
        # fallback: just print the first 50 lines
        lines = report.split("\n")[:50]
        print()
        for line in lines:
            print(f"  {line}")
        if len(report.split("\n")) > 50:
            print(f"  {_c(f'… ({len(report.split(chr(10)))} lines total. Install less for full pager.)', 'dim')}")
        print()

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
        # Offer full-screen viewer for long reports
        report = result.report_markdown or ""
        if len(report) > 1200:
            print(_c("  Type /view to browse the full report in a pager.", "dim"))
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
    _init_highlighting()

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
                print(f"  {_c('Use @ to attach files, $ to run shell commands, \\ for multi-line,', 'dim')}")
                print(f"  {_c('/editor to open text editor, /view to browse reports.', 'dim')}")
                _empty_hint_shown = True
            continue
        _empty_hint_shown = False

        first = text.split()[0].lower()

        # Shell mode: $ command → run and add output as evidence
        if first.startswith("$") and len(first) > 1:
            _append_history(text)
            _handle_shell(text, session)
            continue

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

        elif first == "/history":
            parts = text.split()
            n = 20
            if len(parts) > 1:
                try:
                    n = int(parts[1])
                except ValueError:
                    pass
            _show_history(n)

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

        elif first == "/view":
            _handle_view(session)

        elif first == "/verbose":
            session.verbose = not session.verbose
            state = _c("on", "green") if session.verbose else _c("off", "dim")
            print(f"\n  Verbose: {state}  ({_c('shows full thinking text', 'dim')})\n")

        elif first == "/editor":
            editor_text = _handle_editor(session)
            if editor_text:
                _append_history(editor_text)
                expanded, file_errors = _expand_file_refs(editor_text)
                for err in file_errors:
                    print(err)
                try:
                    _run_turn(expanded, session)
                except KeyboardInterrupt:
                    print(f"\n  {_c('⊘', 'yellow')}  Stopped.\n")

        else:
            _append_history(text)
            expanded, file_errors = _expand_file_refs(text)
            for err in file_errors:
                print(err)
            try:
                _run_turn(expanded, session)
            except KeyboardInterrupt:
                print(f"\n  {_yellow('⊘')}  Stopped.  {_dim('Continue asking or type /exit to quit.')}\n")
