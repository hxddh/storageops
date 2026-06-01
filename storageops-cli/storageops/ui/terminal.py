"""ANSI terminal formatting utilities — shared across CLI and REPL."""
from __future__ import annotations

import sys

_IS_TTY = sys.stdout.isatty()

_CODES = {
    "reset": 0, "bold": 1, "dim": 2, "italic": 3,
    "green": 32, "yellow": 33, "red": 31, "cyan": 36,
    "magenta": 35, "blue": 34, "white": 37,
}


def c(text: str, *args: str) -> str:
    """Apply ANSI codes. No-ops when stdout is not a TTY."""
    if not _IS_TTY:
        return text
    codes = [str(_CODES.get(a, a)) for a in args]
    return "\033[" + ";".join(codes) + "m" + text + "\033[0m"


def bold(t: str) -> str:    return c(t, "bold")
def dim(t: str) -> str:     return c(t, "dim")
def green(t: str) -> str:   return c(t, "green")
def yellow(t: str) -> str:  return c(t, "yellow")
def red(t: str) -> str:     return c(t, "red")
def cyan(t: str) -> str:    return c(t, "cyan")
def magenta(t: str) -> str: return c(t, "magenta")
def blue(t: str) -> str:    return c(t, "blue")


def hr(width: int = 60, char: str = "─") -> str:
    return dim(char * width)


def err(msg: str) -> None:
    print("  " + red("✗") + " " + msg, file=sys.stderr)


def warn(msg: str) -> None:
    print("  " + yellow("⚠") + " " + msg, file=sys.stderr)


def ok(msg: str) -> None:
    print("  " + green("✓") + " " + msg)


def is_tty() -> bool:
    return _IS_TTY
