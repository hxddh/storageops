"""Unified tool interface for StorageOps.

Tool calls flow through here:
  LLM → Pi RPC (tool_use event) → Agent → Tools.execute() → result → Pi

Tools are dispatched via tool_bridge.py subprocess, which maps tool names
to core parsers/analyzers in storageops-core.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from storageops.core.event import ToolCall, ToolResult


# ── Tool registry ────────────────────────────────────────────────────

class ToolRegistry:
    """Registry of available StorageOps tools with execution dispatch."""

    def __init__(self, bridge_path: Path | None = None) -> None:
        self._bridge_path = bridge_path or self._default_bridge_path()
        self._tool_names: set[str] = set()

    @staticmethod
    def _default_bridge_path() -> Path:
        """Locate tool_bridge.py relative to this file."""
        here = Path(__file__).resolve().parent
        runtime = here.parent / "runtime" / "tool_bridge.py"
        if runtime.exists():
            return runtime
        # Fallback: search
        for p in Path(__file__).resolve().parents:
            candidate = p / "runtime" / "tool_bridge.py"
            if candidate.exists():
                return candidate
        return Path("tool_bridge.py")

    def execute(self, call: ToolCall, timeout: float = 30.0) -> ToolResult:
        """Execute a tool call via tool_bridge.py subprocess.

        Returns a ToolResult with ok, summary, and error fields.
        """
        t0 = time.monotonic()
        input_json = json.dumps({
            "tool": call.name,
            "inputs": call.arguments,
        }, ensure_ascii=False)

        try:
            proc = subprocess.run(
                ["python3", str(self._bridge_path)],
                input=input_json,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed = time.monotonic() - t0

            if proc.returncode != 0:
                # Try to parse error from stderr
                err_text = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
                return ToolResult(
                    id=call.id, name=call.name, ok=False,
                    error=err_text[:500], elapsed=elapsed,
                )

            # Parse JSON result from stdout
            try:
                result = json.loads(proc.stdout)
            except json.JSONDecodeError:
                result = {"raw_output": proc.stdout.strip()}

            summary = self._summarize(call.name, result)
            return ToolResult(
                id=call.id, name=call.name, ok=True,
                summary=summary, elapsed=elapsed, raw=result,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                id=call.id, name=call.name, ok=False,
                error=f"Tool timed out after {timeout}s", elapsed=time.monotonic() - t0,
            )
        except Exception as exc:
            return ToolResult(
                id=call.id, name=call.name, ok=False,
                error=str(exc), elapsed=time.monotonic() - t0,
            )

    def _summarize(self, name: str, result: dict) -> str:
        """Extract a human-readable summary from tool output."""
        parts: list[str] = []

        # Common fields to look for
        for key in ("records", "transfers", "errors", "requests", "signals",
                     "findings", "findings_count", "count"):
            v = result.get(key)
            if isinstance(v, list):
                parts.append(f"{len(v)} {key}")
            elif isinstance(v, int):
                parts.append(f"{v} {key}")

        for key in ("root_cause_type", "root_cause", "domain", "bottleneck",
                     "primary_domain", "conclusion"):
            v = result.get(key)
            if isinstance(v, str) and v:
                parts.append(v.replace("_", " ")[:40])
                break

        for key in ("ok", "valid", "success"):
            v = result.get(key)
            if isinstance(v, bool):
                parts.append("ok" if v else "failed")
                break

        for key in ("confidence",):
            v = result.get(key)
            if isinstance(v, (int, float)):
                parts.append(f"{v:.0%}")

        return "  ".join(parts[:3]) if parts else f"{name} completed"
