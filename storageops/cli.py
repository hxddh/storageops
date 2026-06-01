"""
CLI entry points — all subcommands in one file.

Usage:
    storageops analyze <text|@file>
    storageops triage <text>
    storageops diagnose <text>
    storageops eval [--suite PATH]
    storageops config [--set key=value] [--get key] [--list]
    storageops setup
    storageops doctor
    storageops update
    storageops memory [--search QUERY] [--list]
    storageops audit [--stats] [--list]
    storageops serve [--host HOST] [--port PORT]
    storageops resume [SESSION_ID]
    storageops repl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="storageops",
        description="StorageOps — S3-compatible object storage diagnostic toolkit",
    )
    sub = p.add_subparsers(dest="command", help="Subcommands")

    # analyze
    a = sub.add_parser("analyze", help="Run rule-based analysis on evidence text")
    a.add_argument("text", nargs="?", help="Evidence text or @filepath")
    a.add_argument("--domain", help="Force a specific diagnostic domain")
    a.add_argument("--json", action="store_true", help="Output raw JSON")

    # triage
    t = sub.add_parser("triage", help="Classify evidence into a diagnostic domain")
    t.add_argument("text", nargs="?", help="Evidence text or @filepath")

    # diagnose
    d = sub.add_parser("diagnose", help="Run LLM-powered diagnosis via Pi")
    d.add_argument("text", nargs="?", help="Evidence text or @filepath")
    d.add_argument("--session", help="Resume existing session ID")

    # eval
    e = sub.add_parser("eval", help="Run golden test cases")
    e.add_argument("--suite", help="Path to test suite directory")
    e.add_argument("--case", help="Run a specific test case")

    # config
    c = sub.add_parser("config", help="Manage StorageOps configuration")
    c.add_argument("--set", nargs="*", help="Set config values (key=value)")
    c.add_argument("--get", help="Get a config value")
    c.add_argument("--list", action="store_true", help="List all config values")

    # setup
    sub.add_parser("setup", help="Install Pi binary and configure environment")

    # doctor
    sub.add_parser("doctor", help="Run system diagnostics check")

    # update
    sub.add_parser("update", help="Update Pi binary to latest version")

    # memory
    m = sub.add_parser("memory", help="Search or list past sessions")
    m.add_argument("--search", help="Search query for past sessions")
    m.add_argument("--list", action="store_true", help="List recent sessions")

    # audit
    au = sub.add_parser("audit", help="Audit log analysis")
    au.add_argument("--stats", action="store_true", help="Show audit statistics")
    au.add_argument("--list", action="store_true", help="List recent audit sessions")

    # serve
    s = sub.add_parser("serve", help="Start HTTP API server")
    s.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    s.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")

    # resume
    r = sub.add_parser("resume", help="Resume an existing Pi session")
    r.add_argument("session_id", nargs="?", help="Session ID (prompts picker if omitted)")

    # cleanup
    cl = sub.add_parser("cleanup", help="Remove orphaned legacy session files")
    cl.add_argument("--execute", action="store_true", help="Actually delete (default: dry-run)")

    # repl (default)
    sub.add_parser("repl", help="Start interactive REPL")

    return p


def _read_input(text: str | None) -> str:
    """Read text from argument, @file, or stdin."""
    if text and text.startswith("@"):
        path = Path(text[1:]).expanduser()
        if path.is_file():
            return path.read_text(encoding="utf-8")
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    if text:
        return text
    # Read from stdin
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main(argv: list[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = _make_parser()
    args = parser.parse_args(argv)

    if not args.command or args.command == "repl":
        from storageops.repl import repl
        repl()
        return

    cmd = args.command

    if cmd == "analyze":
        _cmd_analyze(args)

    elif cmd == "triage":
        _cmd_triage(args)

    elif cmd == "diagnose":
        _cmd_diagnose(args)

    elif cmd == "eval":
        _cmd_eval(args)

    elif cmd == "config":
        _cmd_config(args)

    elif cmd == "setup":
        _cmd_setup()

    elif cmd == "doctor":
        _cmd_doctor()

    elif cmd == "update":
        _cmd_update()

    elif cmd == "memory":
        _cmd_memory(args)

    elif cmd == "audit":
        _cmd_audit(args)

    elif cmd == "serve":
        _cmd_serve(args)

    elif cmd == "resume":
        _cmd_resume(args)

    elif cmd == "cleanup":
        _cmd_cleanup(args)

    else:
        parser.print_help()


# ── Command Implementations ───────────────────────────────────────────

def _cmd_analyze(args) -> None:
    text = _read_input(args.text)
    if not text:
        print("Error: no evidence text provided", file=sys.stderr)
        sys.exit(1)

    from storageops.diagnostics import classify_evidence, run_analysis

    if args.domain:
        domain = args.domain
    else:
        classification = classify_evidence(text)
        domain = classification["primary_domain"]
        if not args.json:
            print(f"Classified as: {domain}")

    result = run_analysis(domain, text)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        from storageops.diagnostics import generate_report, assess_evidence
        evidence = assess_evidence(text, domain)
        report = generate_report(domain, dict(result), evidence.get("quality", "partial"))
        print(report)


def _cmd_triage(args) -> None:
    text = _read_input(args.text)
    if not text:
        print("Error: no evidence text provided", file=sys.stderr)
        sys.exit(1)

    from storageops.diagnostics import classify_evidence, assess_evidence
    from storageops.utils.secret_scanner import scan

    scan_result = scan(text)
    safe_text = scan_result["redacted_text"]

    classification = classify_evidence(safe_text)
    domain = classification["primary_domain"]
    evidence = assess_evidence(safe_text, domain)

    print(json.dumps({
        "primary_domain": domain,
        "all_domains": classification["all_domains"],
        "scores": classification["scores"],
        "evidence_quality": evidence.get("quality", "unknown"),
        "missing_required": evidence.get("missing_required", []),
        "missing_helpful": evidence.get("missing_helpful", []),
        "secrets_redacted": scan_result["count"],
    }, indent=2, ensure_ascii=False))


def _cmd_diagnose(args) -> None:
    """LLM-powered diagnosis using Pi."""
    text = _read_input(args.text)
    if not text and not args.session:
        print("Error: provide evidence text or --session to resume", file=sys.stderr)
        sys.exit(1)

    from storageops.session import create, load as load_session
    from storageops.agent import converse_one_shot, converse
    from storageops.display import Display

    display = Display()

    if args.session:
        session = load_session(args.session)
        if not session:
            print(f"Session not found: {args.session}", file=sys.stderr)
            sys.exit(1)
        converse(session, text, display)
    else:
        # One-shot mode
        from storageops.context import build_prompt
        session = create(cwd=os.getcwd())
        prompt = build_prompt(session, text)
        result = converse_one_shot(prompt)

        if result.text:
            print(result.text)
        if result.errors:
            print("\nErrors:", file=sys.stderr)
            for e in result.errors:
                print(f"  {e}", file=sys.stderr)


def _cmd_eval(args) -> None:
    """Run golden test cases."""
    from storageops.analyzers.eval_runner import main as eval_main
    eval_argv = []
    if args.suite:
        eval_argv.extend(["--suite", args.suite])
    if args.case:
        eval_argv.extend(["--case", args.case])
    eval_main(eval_argv if eval_argv else None)


def _cmd_config(args) -> None:
    """Manage configuration."""
    from storageops.config import load, save, update

    if args.list:
        cfg = load()
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return

    if args.get:
        cfg = load()
        print(cfg.get(args.get, ""))
        return

    if args.set:
        for pair in args.set:
            if "=" in pair:
                k, v = pair.split("=", 1)
                update(**{k.strip(): v.strip()})
        print("Configuration updated.")
        return

    # No flags: show current config
    cfg = load()
    if cfg:
        for k, v in cfg.items():
            # Redact api_key
            if k == "api_key" and v:
                v = v[:4] + "..." + v[-4:] if len(v) > 8 else "***"
            print(f"  {k}: {v}")
    else:
        print("No configuration set. Use `storageops config --set key=value`")


def _cmd_setup() -> None:
    """Run setup: install Pi binary and configure environment."""
    from storageops.pi_installer import is_installed, download_pi, ensure_path_entry

    print("StorageOps Setup")
    print("=" * 40)

    if is_installed():
        print("✓ Pi binary already installed")
    else:
        print("Downloading Pi binary...")
        try:
            path = download_pi()
            print(f"✓ Pi installed at: {path}")
        except Exception as exc:
            print(f"✗ Failed to download Pi: {exc}", file=sys.stderr)
            sys.exit(1)

    if ensure_path_entry():
        print("✓ Added ~/.storageops/bin to PATH. Restart your shell to apply.")

    # Check API key
    from storageops.config import get_api_key
    if get_api_key():
        print("✓ API key configured")
    else:
        print("⚠ No API key found. Run: storageops config --set api_key=YOUR_KEY")

    print("\nSetup complete. Run `storageops repl` to start.")


def _cmd_doctor() -> None:
    """Run system diagnostics."""
    import platform
    from storageops.config import get_api_key, get_pi_command
    from storageops.pi_installer import is_installed

    print("StorageOps Doctor")
    print("=" * 40)

    # Python
    print(f"  Python: {platform.python_version()}")

    # Pi binary
    pi_cmd = get_pi_command()
    if is_installed():
        print(f"  Pi binary: ✓ ({pi_cmd})")
    else:
        print(f"  Pi binary: ✗ not found ({pi_cmd})")

    # API key
    if get_api_key():
        print("  API key: ✓ configured")
    else:
        print("  API key: ✗ not configured")

    # Directories
    home = Path.home() / ".storageops"
    for dname in ["sessions", "bin"]:
        d = home / dname
        print(f"  ~/.storageops/{dname}: {'✓' if d.exists() else '○ (not created yet)'}")

    # Package
    try:
        import storageops
        print(f"  storageops package: ✓ ({storageops.__file__})")
    except ImportError:
        print("  storageops package: ✗ not importable")


def _cmd_update() -> None:
    """Update Pi binary."""
    from storageops.pi_installer import download_pi

    print("Updating Pi binary...")
    try:
        path = download_pi()
        print(f"✓ Pi updated at: {path}")
    except Exception as exc:
        print(f"✗ Update failed: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_memory(args) -> None:
    """Search or list past sessions."""
    from storageops.session import list_all

    if args.list:
        results = list_all()
    elif args.search:
        results = list_all(query=args.search)
    else:
        results = list_all()

    if not results:
        print("No sessions found.")
        return

    for r in results[:20]:
        sid = r.get("id", "")[:8]
        summary = (r.get("summary") or "(no summary)")[:60]
        domain = r.get("domain", "")
        turns = r.get("turns", 0)
        created = (r.get("created", "") or "")[:16]
        print(f"  {sid}... [{domain}] ({turns}t) {created}  {summary}")


def _cmd_audit(args) -> None:
    """Audit log analysis."""
    from storageops.audit_reader import compute_stats, list_sessions

    if args.stats:
        stats = compute_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))
    elif args.list:
        sessions = list_sessions()
        for s in sessions:
            print(f"  {s['session_id'][:8]}... [{s['domain']}] {s['outcome']}  {s['ts']}")
    else:
        sessions = list_sessions(limit=10)
        for s in sessions:
            print(f"  {s['session_id'][:8]}... [{s['domain']}] {s['outcome']}  {s['ts']}")


def _cmd_serve(args) -> None:
    """Start HTTP API server."""
    from storageops.api_server import run
    run(host=args.host, port=args.port)


def _cmd_resume(args) -> None:
    """Resume an existing Pi session."""
    from storageops.session import load as load_session, list_all
    from storageops.display import Display

    display = Display()

    sid = args.session_id
    if not sid:
        # Picker mode
        results = list_all()[:20]
        if not results:
            print("No sessions found.", file=sys.stderr)
            sys.exit(1)
        for i, r in enumerate(results):
            print(f"  [{i}] {r.get('id','')[:8]}... {(r.get('summary') or '')[:60]}")
        try:
            choice = input("Resume which session? [0]: ").strip()
            idx = int(choice) if choice else 0
            sid = results[idx]["id"]
        except (ValueError, KeyboardInterrupt):
            sys.exit(0)

    session = load_session(sid)
    if not session:
        print(f"Session not found: {sid}", file=sys.stderr)
        sys.exit(1)

    print(f"Resumed session: {sid[:8]}...")
    print(f"  Turns: {session.meta().get('turns', 0)}")
    display.show_slash_result("Enter your prompt (empty line to finish):")


def _cmd_cleanup(args) -> None:
    """Remove orphaned legacy .json session files."""
    from storageops.session import cleanup_orphans

    execute = getattr(args, "execute", False)
    mode = "deleting" if execute else "DRY RUN — would delete"
    print(f"Scanning for orphan session files ({mode})...")

    orphans = cleanup_orphans(dry_run=not execute)
    if not orphans:
        print("  No orphan files found.")
    else:
        for f in orphans:
            print(f"  {f}")
        print(f"\n  {len(orphans)} orphan(s) {'removed' if execute else 'found'}.")
        if not execute:
            print("  Run with --execute to delete them.")


if __name__ == "__main__":
    main()
