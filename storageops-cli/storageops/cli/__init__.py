"""StorageOps CLI — argument parser and main entry point.

Commands are split into sub-modules under cli/ for maintainability.
"""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="storageops",
        description="S3-compatible object storage diagnostic CLI",
    )
    sub = p.add_subparsers(dest="command", help="Command")

    # triage
    sp_triage = sub.add_parser("triage", help="Classify evidence")
    sp_triage.add_argument("file")
    sp_triage.add_argument("--format", choices=["human", "json"], default="human")

    # analyze
    sp_analyze = sub.add_parser("analyze", help="Run parser + analyzer pipeline")
    sp_analyze.add_argument("domain")
    sp_analyze.add_argument("file")
    sp_analyze.add_argument("--format", choices=["human", "json"], default="human")
    sp_analyze.add_argument("--no-redact", action="store_true")
    sp_analyze.add_argument("--exit-code", action="store_true")

    # diagnose / agent
    sp_diag = sub.add_parser("diagnose", help="Full Pi agent diagnosis (aliases: agent)")
    sp_diag.add_argument("file")
    sp_diag.add_argument("--format", choices=["human", "json"], default="human")
    sp_diag.add_argument("--stream", action="store_true")
    sp_diag.add_argument("--max-turns", type=int, default=8)
    sp_diag.add_argument("--timeout-seconds", type=int, default=600)
    sp_diag.add_argument("--pi-command")
    sp_diag.add_argument("--pi-model")
    sp_diag.add_argument("--pi-provider")
    sp_diag.add_argument("--verbose", action="store_true")
    sp_diag.add_argument("--exit-code", action="store_true")

    sp_agent = sub.add_parser("agent", help="Alias for diagnose")
    # Copy same args
    for a in sp_diag._actions:
        if a.dest not in ("help",):
            sp_agent._add_action(a)

    # batch
    sp_batch = sub.add_parser("batch", help="Triage multiple files")
    sp_batch.add_argument("files", nargs="+")
    sp_batch.add_argument("--format", choices=["human", "json"], default="human")
    sp_batch.add_argument("--output")

    # scan (alias for batch)
    sp_scan = sub.add_parser("scan", help="Alias for batch")
    sp_scan.add_argument("files", nargs="+")
    sp_scan.add_argument("--format", choices=["human", "json"], default="human")
    sp_scan.add_argument("--output")

    # report
    sp_report = sub.add_parser("report", help="Render markdown from analysis JSON")
    sp_report.add_argument("file")

    # eval
    sp_eval = sub.add_parser("eval", help="Golden case evaluation")
    sp_eval.add_argument("--case")
    sp_eval.add_argument("--all", action="store_true")
    sp_eval.add_argument("--regression", action="store_true")
    sp_eval.add_argument("--cases-dir", default="agents/skills/storageops-eval-golden-cases/cases")
    sp_eval.add_argument("--outputs-dir")
    sp_eval.add_argument("--metrics-file")
    sp_eval.add_argument("--threshold", type=float, default=0.10)

    # resume
    sp_resume = sub.add_parser("resume", help="Resume past session")
    sp_resume.add_argument("session_id", nargs="?")
    sp_resume.add_argument("--list", action="store_true")

    # config
    sp_cfg = sub.add_parser("config", help="View/modify configuration")
    sp_cfg.add_argument("config_action", nargs="?", choices=["list", "get", "set"], default="list")
    sp_cfg.add_argument("key", nargs="?")
    sp_cfg.add_argument("value", nargs="?")

    # update
    sp_upd = sub.add_parser("update", help="Update Pi binary and skills")
    sp_upd.add_argument("--check", action="store_true")

    # setup
    sub.add_parser("setup", help="Configure Pi Agent, API key, skills")

    # doctor
    sub.add_parser("doctor", help="Check installation health")

    # memory
    sp_mem = sub.add_parser("memory", help="Browse/search past cases")
    sp_mem.add_argument("memory_action", nargs="?",
                        choices=["list", "search", "save", "export", "import"],
                        default="list")
    sp_mem.add_argument("query", nargs="*")
    sp_mem.add_argument("--domain")
    sp_mem.add_argument("--limit", type=int, default=20)
    sp_mem.add_argument("--format", choices=["human", "json"], default="human")
    sp_mem.add_argument("--root-cause")
    sp_mem.add_argument("--summary")
    sp_mem.add_argument("--keywords")
    sp_mem.add_argument("--output")
    sp_mem.add_argument("--input-file")
    sp_mem.add_argument("--merge", action="store_true")

    # audit
    sp_audit = sub.add_parser("audit", help="Audit log")
    sp_audit.add_argument("audit_action", nargs="?",
                          choices=["list", "show", "stats"], default="list")
    sp_audit.add_argument("session_id", nargs="?")
    sp_audit.add_argument("--limit", type=int, default=50)
    sp_audit.add_argument("--format", choices=["human", "json"], default="human")
    sp_audit.add_argument("--verbose", action="store_true")

    # mcp
    sub.add_parser("mcp", help="Start MCP stdio server")

    # serve
    sp_serve = sub.add_parser("serve", help="Start HTTP API server")
    sp_serve.add_argument("--host", default="0.0.0.0")
    sp_serve.add_argument("--port", type=int, default=8080)
    sp_serve.add_argument("--reload", action="store_true")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        # No command → start REPL
        from storageops.ui.repl import run_repl
        run_repl()
        return

    dispatch(args)


def dispatch(args: argparse.Namespace) -> None:
    cmd = args.command

    if cmd == "triage":
        from storageops.cli.triage import cmd_triage
        cmd_triage(args)

    elif cmd == "analyze":
        from storageops.cli.analyze import cmd_analyze
        cmd_analyze(args)

    elif cmd in ("diagnose", "agent"):
        from storageops.cli.diagnose import cmd_diagnose
        cmd_diagnose(args)

    elif cmd == "batch":
        from storageops.cli.triage import cmd_batch
        cmd_batch(args)

    elif cmd == "scan":
        from storageops.cli.triage import cmd_batch
        cmd_batch(args)

    elif cmd == "report":
        from storageops.cli.analyze import cmd_report
        cmd_report(args)

    elif cmd == "eval":
        from storageops.cli.eval import cmd_eval
        cmd_eval(args)

    elif cmd == "resume":
        from storageops.cli.resume_cli import cmd_resume
        cmd_resume(args)

    elif cmd == "config":
        from storageops.cli.config_cli import cmd_config
        cmd_config(args)

    elif cmd == "update":
        from storageops.cli.config_cli import cmd_update
        cmd_update(args)

    elif cmd == "setup":
        from storageops.cli.config_cli import cmd_setup
        cmd_setup(args)

    elif cmd == "doctor":
        from storageops.cli.config_cli import cmd_doctor
        cmd_doctor(args)

    elif cmd == "memory":
        from storageops.cli.memory import cmd_memory
        cmd_memory(args)

    elif cmd == "audit":
        from storageops.cli.audit import cmd_audit
        cmd_audit(args)

    elif cmd == "mcp":
        from storageops.mcp_server import run_mcp_server
        run_mcp_server()

    elif cmd == "serve":
        from storageops.cli.serve import cmd_serve
        cmd_serve(args)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


# Legacy exports for `from storageops.cli import cmd_triage` etc.
from storageops.cli.triage import cmd_triage, cmd_batch  # noqa: F401
cmd_scan = cmd_batch  # alias
from storageops.cli.analyze import cmd_analyze, cmd_report  # noqa: F401
from storageops.cli.diagnose import cmd_diagnose  # noqa: F401
cmd_agent = cmd_diagnose  # alias
from storageops.cli.eval import cmd_eval  # noqa: F401
from storageops.cli.resume_cli import cmd_resume  # noqa: F401
from storageops.cli.config_cli import cmd_config, cmd_setup, cmd_doctor, cmd_update  # noqa: F401
from storageops.cli.memory import cmd_memory  # noqa: F401
from storageops.cli.audit import cmd_audit  # noqa: F401
from storageops.cli.serve import cmd_serve  # noqa: F401


if __name__ == "__main__":
    main()
