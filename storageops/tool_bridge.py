"""
StorageOps tool bridge — called by the Pi Extension for each tool invocation.

Reads {"tool": "<name>", "inputs": {...}} from stdin.
Writes JSON result to stdout.
"""
from __future__ import annotations

import json
import os
import sys


def _setup_path() -> None:
    """Ensure storageops package is importable from the repo root."""
    # This file is at <repo>/storageops/tool_bridge.py
    # The repo root is one level up
    repo_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def main() -> None:
    _setup_path()
    try:
        data = json.loads(sys.stdin.read())
        tool_name: str = data["tool"]
        inputs: dict = data.get("inputs", {})
    except (json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"error": f"Invalid bridge request: {exc}"}))
        sys.exit(1)

    try:
        from storageops.tool_registry import dispatch_tool
        result = dispatch_tool(tool_name, inputs)
    except Exception as exc:
        result = {"error": str(exc), "tool": tool_name}

    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
