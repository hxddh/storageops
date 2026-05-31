"""Minimal agent runtime contracts for StorageOps.

StorageOps owns offline diagnostics and safety gates. Agent-loop concerns are
implemented by external runtimes; v0.3 supports Pi Coding Agent only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentRunOptions:
    """Options accepted by the StorageOps agent runtime facade."""

    runtime: str = "pi"
    stream: bool = False
    max_turns: int = 8
    timeout_seconds: int = 600
    pi_command: str = "pi"
    pi_model: str | None = None
    pi_provider: str | None = None
    verbose: bool = False
    # Called with each raw Pi event as it arrives; used for live progress display.
    event_callback: Callable[[dict[str, Any]], None] | None = None


@dataclass
class AgentRunResult:
    """Structured result returned by an agent runtime."""

    ok: bool
    runtime: str
    report_markdown: str = ""
    raw_events: list[dict] = field(default_factory=list)
    error: str | None = None
