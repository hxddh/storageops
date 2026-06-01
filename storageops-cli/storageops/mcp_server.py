"""
StorageOps MCP server — exposes diagnostic tools over Model Context Protocol.

Usage:
    python -m storageops.mcp_server
    storageops mcp

Configure in Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "storageops": {
          "command": "storageops",
          "args": ["mcp"]
        }
      }
    }

Requires: pip install storageops[mcp]
"""
from __future__ import annotations

import json
import sys


def run_mcp_server() -> None:
    """Start the MCP server. Requires `mcp` package."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
        import asyncio
    except ImportError:
        print(
            "MCP server requires the mcp package.\n"
            "Install it with: pip install 'mcp[cli]'",
            file=sys.stderr,
        )
        sys.exit(1)

    from storageops.tool_registry import TOOL_DEFINITIONS, dispatch_tool

    server = Server("storageops")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("input_schema", {"type": "object", "properties": {}}),
            )
            for t in TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        result = dispatch_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]

    async def main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(main())


if __name__ == "__main__":
    run_mcp_server()
