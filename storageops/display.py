"""
Streaming terminal output with ANSI escape codes.

All rendering is inline — no separate terminal.py dependency.
Checks isatty() to disable colors when piped.
"""
from __future__ import annotations

import shutil
import sys
import time


def is_tty() -> bool:
    """Check if stdout is a terminal (supports ANSI codes)."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# ── ANSI helpers ──────────────────────────────────────────────────────

def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if is_tty() else text


def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m" if is_tty() else text


def _green(text: str) -> str:
    return f"\033[32m{text}\033[0m" if is_tty() else text


def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m" if is_tty() else text


def _cyan(text: str) -> str:
    return f"\033[36m{text}\033[0m" if is_tty() else text


def cursor_up(n: int = 1) -> None:
    if is_tty():
        sys.stdout.write(f"\033[{n}A")


def clear_line() -> None:
    if is_tty():
        sys.stdout.write("\033[2K\r")


# ── Progress spinner ──────────────────────────────────────────────────

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Display:
    """Streaming terminal output renderer for the Pi conversation loop."""

    def __init__(self) -> None:
        self._spinner_idx = 0
        self._term_width = shutil.get_terminal_size().columns

    def show_thinking(self, text: str) -> None:
        """Show thinking text in dim grey with spinner prefix."""
        if not is_tty():
            return
        # Truncate to one line for thinking display
        line = text.replace("\n", " ").strip()
        if len(line) > self._term_width - 6:
            line = line[: self._term_width - 9] + "..."
        frame = _SPINNER_FRAMES[self._spinner_idx % len(_SPINNER_FRAMES)]
        self._spinner_idx += 1
        clear_line()
        sys.stdout.write(f"{_dim('  ' + frame)} {_dim(line)}\n")
        sys.stdout.flush()

    def show_text_delta(self, text: str) -> None:
        """Stream text output character by character."""
        sys.stdout.write(text)
        sys.stdout.flush()

    def show_tool_call(self, name: str, args: dict) -> None:
        """Show tool invocation in yellow with dim args summary."""
        args_str = _format_args(args)
        sys.stdout.write(f"\n{_yellow(f'  ⚙ {name}')} {_dim(args_str)}\n")
        sys.stdout.flush()

    def show_tool_result(self, name: str, summary: str) -> None:
        """Show tool result in green."""
        sys.stdout.write(f"{_green(f'  ✓ {name}')} {_dim(f'→ {summary}')}\n")
        sys.stdout.flush()

    def show_result(self, elapsed_ms: float) -> None:
        """Show elapsed time."""
        if elapsed_ms >= 1000:
            time_str = f"{elapsed_ms / 1000:.1f}s"
        else:
            time_str = f"{elapsed_ms:.0f}ms"
        sys.stdout.write(f"\n{_dim(f'  ⏱ {time_str}')}\n")
        sys.stdout.flush()

    def show_progress(self, total: int, current: int) -> None:
        """Show a progress bar if tty, otherwise step counter."""
        if not is_tty():
            if current % 10 == 0 or current == total:
                sys.stdout.write(f"\r[{current}/{total}]")
                sys.stdout.flush()
            return

        width = min(40, self._term_width - 20)
        pct = current / max(total, 1)
        filled = int(width * pct)
        bar = "█" * filled + "░" * (width - filled)
        clear_line()
        sys.stdout.write(f"  [{bar}] {current}/{total}")
        sys.stdout.flush()
        if current == total:
            sys.stdout.write("\n")

    def show_error(self, msg: str) -> None:
        """Show error message in red."""
        sys.stdout.write(f"\n{_red(f'  ✗ Error: {msg}')}\n")
        sys.stdout.flush()

    def show_banner(self, session_id: str = "", version: str = "0.3.0") -> None:
        """Show welcome banner."""
        banner = f"""
{_cyan('╔══════════════════════════════════════════╗')}
{_cyan('║')}       StorageOps v{version:<27}{_cyan('║')}
{_cyan('║')}       Object Storage Diagnostic Toolkit  {_cyan('║')}
{_cyan('╚══════════════════════════════════════════╝')}
"""
        sys.stdout.write(banner)
        if session_id:
            sys.stdout.write(f"  Session: {_dim(session_id[:8])}...\n\n")
        sys.stdout.flush()

    def show_slash_result(self, text: str) -> None:
        """Show output from slash commands."""
        sys.stdout.write(f"{text}\n")
        sys.stdout.flush()


def _format_args(args: dict) -> str:
    """Format tool call arguments as a short summary string."""
    if not args:
        return "{}"
    keys = list(args.keys())
    if len(keys) <= 2:
        parts = []
        for k in keys:
            v = args[k]
            if isinstance(v, str) and len(v) > 40:
                v = v[:37] + "..."
            elif isinstance(v, (list, dict)):
                v = f"[{len(v)} items]"
            parts.append(f"{k}={v}")
        return ", ".join(parts)
    return f"({len(keys)} args)"
