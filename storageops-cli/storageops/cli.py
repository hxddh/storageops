"""
StorageOps CLI v0.3

Usage:
    storageops triage <evidence-file>
    storageops analyze <domain> <evidence-file>
    storageops report <analysis-json>
    storageops eval --cases-dir <dir> [--outputs-dir <dir>]
    storageops agent <evidence-file> [--runtime pi] [--stream]

All commands operate on offline artifacts only. No cloud connections.
"""
import argparse
import json
import sys
import re
from pathlib import Path

# storageops/__init__.py adds storageops-core to sys.path on first import;
# importing anything from this package triggers that setup.
from signatures import auto_detect, SIGNATURES  # noqa: F401 — side-effect import


# ── Domain routing ────────────────────────────────────────────────────

SKILL_ROUTE_MAP = {
    's3_protocol_compatibility': 'storageops-s3-protocol-compatibility',
    'cli_sdk_behavior': 'storageops-cli-sdk-diagnosis',
    'performance_throughput': 'storageops-performance-diagnosis',
    'mount_filesystem_workspace': 'storageops-mount-filesystem-workspace',
    'network_endpoint_access': 'storageops-network-endpoint-access',
    'security_iam_policy': 'storageops-security-iam-policy',
    'lifecycle_cost': 'storageops-lifecycle-cost',
}


# ── Commands ──────────────────────────────────────────────────────────

def cmd_triage(args):
    """Triage: classify evidence and suggest routing."""
    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"File not found: {args.file}"}))
        sys.exit(1)

    text = path.read_text(encoding='utf-8', errors='replace')

    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(text)

    detections = auto_detect(text)

    input_type = 'unknown'
    if re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}.*DEBUG', text):
        input_type = 'log_file'
    elif re.search(r'<\?xml.*<Error>', text, re.IGNORECASE):
        input_type = 'error_message'
    elif re.search(r'access_key_id|endpoint.*https?://', text, re.IGNORECASE):
        input_type = 'config_file'
    elif re.search(r'<?xml.*<LifecycleConfiguration>', text, re.IGNORECASE):
        input_type = 'config_file'
    else:
        input_type = 'natural_language'

    primary = detections[0] if detections else {
        'domain': 'unknown_insufficient_evidence',
        'confidence': 0.0,
        'subdomains': [],
    }

    output = {
        "ok": True,
        "module": "triage",
        "input_type": input_type,
        "primary_domain": primary['domain'],
        "primary_confidence": primary['confidence'],
        "severity": "unknown",
        "evidence_quality": "partial" if primary['confidence'] < 0.5 else "sufficient",
        "routing": {
            "primary_skill": SKILL_ROUTE_MAP.get(primary['domain'], 'storageops-triage'),
            "all_detections": detections,
        },
        "secret_scan": {
            "findings_count": secret_result['count'],
            "has_secrets": secret_result['count'] > 0,
        },
        "recommended_next_command": (
            f"storageops analyze {primary['domain']} {args.file}"
            if primary['domain'] != 'unknown_insufficient_evidence'
            else "Provide more detailed evidence (debug logs, error messages, config)"
        ),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def cmd_analyze(args):
    """Analyze: run domain-specific parser + analyzer pipeline."""
    if args.no_redact:
        print(
            "WARNING: --no-redact is active. Output may contain raw credentials. "
            "Do not share or store this output without manual review.",
            file=sys.stderr,
        )
    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"File not found: {args.file}"}))
        sys.exit(1)

    text = path.read_text(encoding='utf-8', errors='replace')
    domain = args.domain

    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(text)
    if secret_result['count'] > 0 and not args.no_redact:
        text = secret_result['redacted_text']

    result = None

    if domain in ('s3_protocol_compatibility', 'sigv4'):
        from parse_sigv4_error import parse_xml_error, diagnose as diagnose_sigv4
        from parse_awscli_debug import parse as parse_awscli
        if '<Code>SignatureDoesNotMatch</Code>' in text:
            result = diagnose_sigv4(parse_xml_error(text))
        else:
            result = parse_awscli(text)

    elif domain in ('cli_sdk_behavior', 'rclone'):
        if 'rclone' in text.lower():
            from parse_rclone_log import parse as parse_rclone
            result = parse_rclone(text)
        elif 's5cmd' in text.lower():
            from parse_s5cmd_error import parse as parse_s5cmd_err
            result = parse_s5cmd_err(text)
        else:
            from parse_awscli_debug import parse as parse_awscli
            result = parse_awscli(text) if 'aws' in text.lower() else {"error": "Unknown CLI tool"}

    elif domain in ('performance_throughput', 'throttling'):
        from parse_s5cmd_log import parse as parse_s5cmd_log
        from parse_awscli_debug import parse as parse_awscli
        from detect_throttling import detect as detect_throttling
        from analyze_throughput import analyze as analyze_throughput

        if 's5cmd' in text.lower():
            parsed = parse_s5cmd_log(text)
        else:
            parsed = parse_awscli(text)

        if args.subdomain == 'throttling' or parsed.get('summary', {}).get('has_throttling'):
            result = detect_throttling(parsed)
        else:
            result = analyze_throughput({
                "object_size_mb": args.object_size or 100,
                "rtt_ms": args.rtt or 50,
                "bandwidth_mbps": args.bandwidth or 1000,
                "observed_throughput_mbps": 50,
            })

    elif domain == 'security_iam_policy':
        from analyze_policy import analyze as analyze_policy, analyze_inline_403
        try:
            result = analyze_policy(json.loads(text))
        except json.JSONDecodeError:
            result = analyze_inline_403(text)

    elif domain == 'lifecycle_cost':
        from analyze_cost import analyze as analyze_cost
        try:
            cost_data = json.loads(text)
        except json.JSONDecodeError:
            cost_data = {
                "storage_price_per_gb": {"STANDARD": 0.023, "STANDARD_IA": 0.0125},
                "prefixes": [],
                "note": "Could not parse JSON. Provide inventory data as JSON.",
            }
        result = analyze_cost(cost_data)

    elif domain == 'mount_filesystem_workspace':
        from analyze_metadata_amplification import analyze as analyze_amp
        try:
            amp_data = json.loads(text)
        except json.JSONDecodeError:
            amp_data = {
                "rtt_ms": 50,
                "syscalls": {"stat": 10000, "open": 2000, "readdir": 200},
                "operation_name": "git status",
                "note": "Using default syscall profile. Provide strace data for accurate analysis.",
            }
        result = analyze_amp(amp_data)

    elif domain == 'network_endpoint_access':
        result = {
            "ok": True,
            "module": "network_diagnosis",
            "note": (
                "Network diagnosis requires live tools. Run manually:\n"
                "  dig <endpoint-hostname>\n"
                "  curl -v --connect-timeout 5 https://<endpoint>\n"
                "  mtr -r -c 10 <endpoint-hostname>"
            ),
            "recommendations": [
                "Collect DNS resolution, TCP connectivity, TLS handshake, and RTT data.",
                "Use storageops-network-endpoint-access Skill for manual diagnosis guidance.",
            ],
        }
    else:
        result = {"ok": False, "error": f"Unknown domain: {domain}"}

    if result is None:
        result = {"ok": False, "error": "Analysis produced no results"}

    result["ok"] = True
    result["module"] = f"analyze_{domain}"
    result["redacted"] = secret_result['count'] > 0 and not args.no_redact
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


def cmd_report(args):
    """Generate a markdown report from analysis JSON."""
    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"File not found: {args.file}"}))
        sys.exit(1)

    data = json.loads(path.read_text())
    domain = data.get('module', data.get('category', 'unknown')).replace('analyze_', '')
    confidence = data.get('confidence', data.get('primary_confidence', 'N/A'))
    conclusion = data.get('conclusion', data.get('note', 'See Key Evidence for analysis details.'))

    report = f"""---
category: {domain}
root_cause_type: unknown
confidence: {confidence}
severity: medium
---

## Summary

{conclusion}

## Key Evidence

```json
{json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000]}
```

## Remediation

{_format_recommendations(data)}

## Safety Notes

- Review all recommendations before executing.
- Label any cloud-mutating command with `# manual-only:` before running.

---
*Generated by StorageOps CLI. Verify all conclusions before acting.*
"""
    print(report)


def _format_recommendations(data: dict) -> str:
    recs = data.get('recommendations') or data.get('recommendation')
    if isinstance(recs, list):
        return '\n'.join(f'- {r}' for r in recs) or '- See Key Evidence section.'
    if isinstance(recs, str) and recs:
        return f'- {recs}'
    if isinstance(recs, dict):
        return '\n'.join(f'- {k}: {v}' for k, v in recs.items())
    return '- See Key Evidence section.'


def cmd_eval(args):
    """Run golden case evaluation or regression check."""
    if getattr(args, 'regression', False):
        _cmd_eval_regression(args)
        return

    from eval_runner import evaluate_case, evaluate_all
    cases_dir = Path(args.cases_dir)
    outputs_dir = Path(args.outputs_dir) if args.outputs_dir else Path('.')

    if args.case:
        case_path = cases_dir / args.case
        output_path = outputs_dir / f"{args.case}.md"
        if not output_path.exists():
            print(json.dumps({"ok": False, "error": f"Output not found: {output_path}"}))
            sys.exit(1)
        output_text = output_path.read_text(encoding='utf-8', errors='replace')
        result = evaluate_case(case_path, output_text)
    elif args.all:
        result = evaluate_all(cases_dir, outputs_dir)
    else:
        print(json.dumps({"ok": False, "error": "Specify --case, --all, or --regression"}))
        sys.exit(1)

    result["ok"] = True
    result["module"] = "eval"
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result.get('passed', True):
        if isinstance(result.get('passed'), bool) and not result['passed']:
            sys.exit(1)
        elif isinstance(result.get('cases'), list):
            if sum(1 for c in result['cases'] if not c.get('passed', True)) > 0:
                sys.exit(1)


def _cmd_eval_regression(args):
    """Compare latest two metric snapshots for confidence regressions."""
    metrics_file = Path(getattr(args, 'metrics_file', None) or
                        Path(__file__).parent.parent.parent / "storageops-eval-metrics.json")
    threshold = getattr(args, 'threshold', 0.10)

    if not metrics_file.exists():
        print(json.dumps({"ok": False, "error": f"Metrics file not found: {metrics_file}"}))
        sys.exit(1)

    try:
        history = json.loads(metrics_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": f"Cannot read metrics: {exc}"}))
        sys.exit(1)

    if len(history) < 2:
        print(json.dumps({
            "ok": True,
            "regressions": [],
            "message": "Need at least 2 metric snapshots; only 1 found.",
        }))
        return

    prev_conf: dict[str, float] = history[-2].get("confidence", {})
    curr_conf: dict[str, float] = history[-1].get("confidence", {})

    regressions = []
    improvements = []
    for case, curr in curr_conf.items():
        prev = prev_conf.get(case)
        if prev is None or prev < 0 or curr < 0:
            continue
        delta = curr - prev
        entry = {"case": case, "prev": round(prev, 4), "curr": round(curr, 4),
                 "delta": round(delta, 4)}
        if delta < -threshold:
            regressions.append(entry)
        elif delta > threshold:
            improvements.append(entry)

    result = {
        "ok": True,
        "module": "eval_regression",
        "prev_ts": history[-2].get("ts", "?"),
        "curr_ts": history[-1].get("ts", "?"),
        "threshold": threshold,
        "regressions": regressions,
        "improvements": improvements,
        "regression_count": len(regressions),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if regressions:
        print(
            f"\nREGRESSION: {len(regressions)} case(s) dropped confidence by >{threshold:.0%}:",
            file=sys.stderr,
        )
        for r in regressions:
            print(f"  {r['case']}: {r['prev']:.2f} → {r['curr']:.2f} ({r['delta']:+.2f})",
                  file=sys.stderr)
        sys.exit(1)


# ── Sub-command handlers ──────────────────────────────────────────────

def cmd_mcp(args):
    """Start the StorageOps MCP server."""
    from storageops.mcp_server import run_mcp_server
    run_mcp_server()


def cmd_serve(args):
    """Start the StorageOps HTTP API server."""
    from storageops.api_server import run
    run(host=args.host, port=args.port, reload=args.reload)


def cmd_memory(args):
    """List or search past diagnosed cases in agent memory."""
    from storageops.memory_store import list_cases, search_cases

    if args.memory_action == "search":
        query = " ".join(args.query)
        results = search_cases(query, domain=getattr(args, 'domain', None), top_k=args.limit)
        print(json.dumps({"query": query, "count": len(results), "results": results},
                         indent=2, ensure_ascii=False))
    else:
        results = list_cases(domain=getattr(args, 'domain', None), limit=args.limit)
        if not results:
            print("No past cases found. Run storageops agent after configuring Pi to build memory.")
            return
        for entry in results:
            ts = entry.get("ts", "")[:19].replace("T", " ")
            domain = entry.get("domain", "?")
            rc = entry.get("root_cause", "unknown")
            session = entry.get("session_id", "")[:8]
            print(f"  [{ts}] [{session}] {domain} → {rc}")
            if args.verbose:
                print(f"    {entry.get('summary', '')[:120]}")


def cmd_audit(args):
    """Show audit log: list sessions, show a session timeline, or print stats."""
    from storageops.audit_reader import list_sessions, get_session, compute_stats

    if args.audit_action == "stats":
        print(json.dumps(compute_stats(), indent=2, ensure_ascii=False))
        return

    if args.audit_action == "show":
        events = get_session(args.session_id)
        if not events:
            print(f"No events found for session {args.session_id!r}", file=sys.stderr)
            sys.exit(1)
        for ev in events:
            ts = ev.get("ts", "")[:19].replace("T", " ")
            event = ev.get("event", "?")
            extra = ""
            if event == "pi_result":
                extra = (f"  ok={ev.get('ok')} redacted={ev.get('redaction_count')} "
                         f"valid={ev.get('validation_ok')} events={ev.get('event_count')}")
            elif event == "tool_call":
                extra = f"  turn={ev.get('turn')} tool={ev.get('tool')} keys={ev.get('input_keys')}"
            elif event == "tool_result":
                status = "ok" if ev.get("ok") else f"err={ev.get('error')}"
                extra = f"  turn={ev.get('turn')} tool={ev.get('tool')} {status}"
            elif event in ("session_start", "session_end"):
                extra = f"  domain={ev.get('domain')} runtime={ev.get('runtime')} outcome={ev.get('outcome')}"
            elif event == "memory_save":
                extra = f"  domain={ev.get('domain')} root_cause={ev.get('root_cause')}"
            print(f"  [{ts}] {event}{extra}")
        return

    sessions = list_sessions(limit=args.limit)
    if not sessions:
        print("No sessions found. Run storageops agent after configuring Pi first.")
        return
    for s in sessions:
        ts = s["ts"]
        sid = s["session_id"]
        domain = s["domain"]
        outcome = s["outcome"]
        runtime = s.get("runtime", "pi")
        tools = ", ".join(sorted(set(s["tools"]))) or "-"
        print(f"  [{ts}] {sid}  {domain:<30} {outcome:<20} runtime={runtime}")
        if getattr(args, "verbose", False):
            print(f"    tools={tools}")


def _result_has_streamed_output(result) -> bool:
    """Return True if Pi already streamed report chunks to stdout."""
    stream_event_types = {"delta", "content_delta", "message_delta", "token", "text"}
    for event in getattr(result, "raw_events", []):
        typ = str(event.get("type") or event.get("event") or "").lower()
        if typ in stream_event_types and (
            event.get("text") or event.get("delta") or event.get("content")
        ):
            return True
    return False


def cmd_agent(args):
    """Run the Pi Coding Agent runtime for offline diagnostics."""
    from storageops.runtime import AgentRunOptions, PiRpcRuntime

    if getattr(args, 'runtime', 'pi') != 'pi':
        print("Only the Pi Coding Agent runtime is supported. Use --runtime pi.", file=sys.stderr)
        sys.exit(2)

    options = AgentRunOptions(
        runtime='pi',
        stream=getattr(args, 'stream', False),
        max_turns=getattr(args, 'max_turns', 8),
        timeout_seconds=getattr(args, 'timeout_seconds', 600),
        pi_command=getattr(args, 'pi_command', 'pi'),
        pi_model=getattr(args, 'pi_model', None),
        pi_provider=getattr(args, 'pi_provider', None),
        verbose=getattr(args, 'verbose', False),
    )
    result = PiRpcRuntime(options).run(args.file)
    if result.ok:
        if not getattr(args, 'stream', False) or not _result_has_streamed_output(result):
            print(result.report_markdown)
        sys.exit(0)
    print(result.error or "Pi runtime failed", file=sys.stderr)
    sys.exit(1)


# ── Argument parser ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='StorageOps CLI — object storage diagnostic toolkit',
        prog='storageops',
    )
    sub = parser.add_subparsers(dest='command', help='Commands')

    # triage
    p_triage = sub.add_parser('triage', help='Classify evidence and route to specialist skill')
    p_triage.add_argument('file', help='Evidence file (log, error, config, description)')
    p_triage.set_defaults(func=cmd_triage)

    # analyze
    p_analyze = sub.add_parser('analyze', help='Run domain-specific parser + analyzer')
    p_analyze.add_argument('domain', help=(
        'Domain: s3_protocol_compatibility, cli_sdk_behavior, '
        'performance_throughput, mount_filesystem_workspace, '
        'network_endpoint_access, security_iam_policy, lifecycle_cost'
    ))
    p_analyze.add_argument('file', help='Evidence file')
    p_analyze.add_argument('--subdomain', default=None, help='Specific subdomain (e.g. throttling)')
    p_analyze.add_argument('--no-redact', action='store_true', help='Skip secret redaction')
    p_analyze.add_argument('--object-size', type=float, help='Object size in MB (for throughput)')
    p_analyze.add_argument('--rtt', type=float, help='RTT in ms (for throughput)')
    p_analyze.add_argument('--bandwidth', type=float, help='Bandwidth in Mbps (for throughput)')
    p_analyze.set_defaults(func=cmd_analyze)

    # report
    p_report = sub.add_parser('report', help='Generate markdown report from analysis JSON')
    p_report.add_argument('file', help='Analysis JSON file')
    p_report.set_defaults(func=cmd_report)

    # eval
    p_eval = sub.add_parser('eval', help='Run golden case evaluation')
    p_eval.add_argument('--cases-dir',
                        default='agents/skills/storageops-eval-golden-cases/cases',
                        help='Golden cases directory')
    p_eval.add_argument('--outputs-dir', default='.', help='Diagnosis outputs directory')
    p_eval.add_argument('--case', help='Single case name')
    p_eval.add_argument('--all', action='store_true', help='Evaluate all cases')
    p_eval.add_argument('--regression', action='store_true',
                        help='Compare latest two snapshots; exit 1 if confidence dropped')
    p_eval.add_argument('--metrics-file', default=None,
                        help='Path to storageops-eval-metrics.json')
    p_eval.add_argument('--threshold', type=float, default=0.10,
                        help='Regression threshold (default: 0.10)')
    p_eval.set_defaults(func=cmd_eval)

    # agent
    p_agent = sub.add_parser('agent', help='Run Pi Coding Agent diagnostic runtime')
    p_agent.add_argument('file', help='Evidence file (log, error, config)')
    p_agent.add_argument('--runtime', choices=['pi'], default='pi',
                         help='Agent runtime (default: pi)')
    p_agent.add_argument('--pi-command', default='pi',
                         help='Pi executable (default: pi)')
    p_agent.add_argument('--pi-model', help='Model name passed through to Pi')
    p_agent.add_argument('--pi-provider', help='Provider name passed through to Pi')
    p_agent.add_argument('--timeout-seconds', type=int, default=600,
                         help='Pi RPC timeout in seconds (default: 600)')
    p_agent.add_argument('--max-turns', type=int, default=8,
                         help='Max Pi agent turns (default: 8)')
    p_agent.add_argument('--verbose', '-v', action='store_true',
                         help='Show runtime diagnostics')
    p_agent.add_argument('--stream', action='store_true',
                         help='Stream Pi output chunks to stdout')
    p_agent.set_defaults(func=cmd_agent)

    # audit
    p_audit = sub.add_parser('audit', help='Inspect agent session audit log')
    audit_sub = p_audit.add_subparsers(dest='audit_action')

    audit_list = audit_sub.add_parser('list', help='List recent agent sessions')
    audit_list.add_argument('--limit', type=int, default=20, help='Max sessions (default 20)')
    audit_list.add_argument('--verbose', '-v', action='store_true',
                            help='Show tool usage per session')

    audit_show = audit_sub.add_parser('show', help='Show full timeline for one session')
    audit_show.add_argument('session_id', help='Session ID (from audit list output)')

    audit_sub.add_parser('stats', help='Aggregate tool frequency and success rate')

    p_audit.set_defaults(func=cmd_audit, audit_action='list', limit=20, verbose=False)

    # mcp
    p_mcp = sub.add_parser('mcp', help='Start MCP server (for Claude Desktop / MCP clients)')
    p_mcp.set_defaults(func=cmd_mcp)

    # serve
    p_serve = sub.add_parser('serve', help='Start HTTP API server (FastAPI)')
    p_serve.add_argument('--host', default='127.0.0.1', help='Bind host (default: 127.0.0.1)')
    p_serve.add_argument('--port', type=int, default=8080, help='Port (default: 8080)')
    p_serve.add_argument('--reload', action='store_true', help='Auto-reload on code changes')
    p_serve.set_defaults(func=cmd_serve)

    # memory
    p_memory = sub.add_parser('memory', help='List or search past diagnosed cases')
    mem_sub = p_memory.add_subparsers(dest='memory_action')

    mem_list = mem_sub.add_parser('list', help='List recent diagnoses')
    mem_list.add_argument('--domain', help='Filter by domain')
    mem_list.add_argument('--limit', type=int, default=20, help='Max entries (default 20)')
    mem_list.add_argument('--verbose', '-v', action='store_true', help='Show summary text')

    mem_search = mem_sub.add_parser('search', help='Search past diagnoses by keyword')
    mem_search.add_argument('query', nargs='+', help='Search keywords')
    mem_search.add_argument('--domain', help='Filter by domain')
    mem_search.add_argument('--limit', type=int, default=5, help='Max results (default 5)')

    p_memory.set_defaults(func=cmd_memory, memory_action='list',
                          domain=None, limit=20, verbose=False)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
