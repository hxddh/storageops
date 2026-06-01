"""CLI: serve and mcp commands."""
from __future__ import annotations

import argparse


def cmd_serve(args: argparse.Namespace) -> None:
    from storageops.api_server import run
    run(host=args.host, port=args.port, reload=args.reload)


# cmd_mcp is handled by the existing mcp_server module
