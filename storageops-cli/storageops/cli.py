"""
StorageOps CLI v0.3

Usage:
    storageops triage <evidence-file>
    storageops analyze <domain> <evidence-file>
    storageops report <analysis-json>
    storageops eval --cases-dir <dir> [--outputs-dir <dir>]
    storageops agent <evidence-file> [--interactive]

All commands operate on offline artifacts only. No cloud connections.
"""
import argparse
import json
import sys
import re
from pathlib import Path

# Resolve storageops-core path relative to this CLI's location
CLI_DIR = Path(__file__).parent.parent
PROJECT_ROOT = CLI_DIR.parent
CORE_DIR = PROJECT_ROOT / 'storageops-core'

# Ensure core modules are importable
for sub in ['utils', 'parsers', 'analyzers']:
    p = str(CORE_DIR / sub)
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Auto-Detection ────────────────────────────────────────────────────

SIGNATURES = {
    's3_protocol_compatibility': [
        (r'SignatureDoesNotMatch', 'sigv4'),
        (r'InvalidSignature', 'sigv4'),
        (r'CanonicalRequest', 'sigv4'),
        (r'StringToSign', 'sigv4'),
        (r'<Code>InvalidPart</Code>', 'multipart_upload'),
        (r'CompleteMultipartUpload', 'multipart_upload'),
        (r'ListObjects', 'list_objects'),
        (r'ETag.*mismatch', 'checksum_etag'),
    ],
    'cli_sdk_behavior': [
        (r'corrupted on transfer', 'rclone'),
        (r'rclone\s+v[\d.]+', 'rclone'),
        (r'size differ', 'rclone'),
        (r'bcecmd', 'bcecmd'),
        (r'obsutil', 'obsutil'),
        (r's5cmd', 's5cmd'),
        (r'botocore\.', 'boto3'),
        (r'aws-cli/', 'awscli'),
    ],
    'performance_throughput': [
        (r'\b429\b', 'throttling'),
        (r'SlowDown', 'throttling'),
        (r'RequestRateLimitExceeded', 'throttling'),
        (r'ThrottlingException', 'throttling'),
        (r'timeout', 'timeout'),
        (r'throughput', 'throughput'),
        (r'MB/s', 'throughput'),
        (r'MiB/s', 'throughput'),
    ],
    'mount_filesystem_workspace': [
        (r'\bfuse\b', 'mount'),
        (r's3fs|bosfs|ossfs|gcsfuse', 'mount'),
        (r'rclone mount', 'mount'),
        (r'掉挂载|mount.*disconnect', 'mount'),
        (r'stat.*storm|metadata.*amplif', 'mount'),
        (r'workspace.*slow', 'mount'),
    ],
    'network_endpoint_access': [
        (r'endpoint.*unreachable|connection refused', 'network'),
        (r'TLS.*error|certificate.*error', 'network'),
        (r'DNS.*fail|NXDOMAIN', 'network'),
        (r'VPC.*endpoint|PrivateLink', 'network'),
        (r'MTU', 'network'),
    ],
    'security_iam_policy': [
        (r'AccessDenied', 'security'),
        (r'Access Denied', 'security'),
        (r'\b403\b', 'security'),
        (r'bucket.*policy|IAM.*policy', 'security'),
        (r'STS.*expir|session.*token.*expir', 'security'),
        (r'KMS.*denied|kms:Decrypt', 'security'),
    ],
    'lifecycle_cost': [
        (r'lifecycle.*rule|LifecycleConfiguration', 'lifecycle'),
        (r'STANDARD_IA|GLACIER|DEEP_ARCHIVE', 'lifecycle'),
        (r'minimum.*storage.*duration', 'lifecycle'),
        (r'retrieval.*cost|request.*cost', 'lifecycle'),
        (r'Intelligent.*Tiering', 'lifecycle'),
    ],
}


def auto_detect(text: str) -> list[dict]:
    """Auto-detect issue domain from evidence text."""
    scores = {}
    for domain, patterns in SIGNATURES.items():
        score = 0
        matches = []
        for pattern, subdomain in patterns:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                score += 1
                matches.append(subdomain)
        if score > 0:
            scores[domain] = {
                'score': score,
                'subdomains': list(set(matches)),
            }

    ranked = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
    return [
        {
            'domain': domain,
            'confidence': min(round(info['score'] / max(1, sum(
                1 for _ in SIGNATURES[domain])), 2), 0.95),
            'subdomains': info['subdomains'],
        }
        for domain, info in ranked
    ]


# ── Commands ──────────────────────────────────────────────────────────

SKILL_ROUTE_MAP = {
    's3_protocol_compatibility': 'storageops-s3-protocol-compatibility',
    'cli_sdk_behavior': 'storageops-cli-sdk-diagnosis',
    'performance_throughput': 'storageops-performance-diagnosis',
    'mount_filesystem_workspace': 'storageops-mount-filesystem-workspace',
    'network_endpoint_access': 'storageops-network-endpoint-access',
    'security_iam_policy': 'storageops-security-iam-policy',
    'lifecycle_cost': 'storageops-lifecycle-cost',
}


def cmd_triage(args):
    """Triage: classify evidence and suggest routing."""
    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"File not found: {args.file}"}))
        sys.exit(1)

    text = path.read_text(encoding='utf-8', errors='replace')

    # Run secret scan first
    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(text)

    # Auto-detect domain
    detections = auto_detect(text)

    # Determine evidence type
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

    # Build output
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
            else "Please provide more detailed evidence (debug logs, error messages, config)"
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

    # Run secret scan
    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(text)
    if secret_result['count'] > 0 and not args.no_redact:
        text = secret_result['redacted_text']

    result = None

    if domain in ('s3_protocol_compatibility', 'sigv4'):
        from parse_sigv4_error import parse_xml_error, diagnose as diagnose_sigv4
        from parse_awscli_debug import parse as parse_awscli

        # Try as XML error first
        if '<Code>SignatureDoesNotMatch</Code>' in text:
            error = parse_xml_error(text)
            result = diagnose_sigv4(error)
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
        from parse_s5cmd_log import parse as parse_s5cmd
        from parse_awscli_debug import parse as parse_awscli
        from detect_throttling import detect as detect_throttling
        from analyze_throughput import analyze as analyze_throughput

        if 's5cmd' in text.lower():
            parsed = parse_s5cmd(text)
        else:
            parsed = parse_awscli(text)

        if args.subdomain == 'throttling' or parsed.get('summary', {}).get('has_throttling'):
            result = detect_throttling(parsed)
        else:
            result = analyze_throughput({
                "object_size_mb": args.object_size or 100,
                "rtt_ms": args.rtt or 50,
                "bandwidth_mbps": args.bandwidth or 1000,
                "observed_throughput_mbps": 50,  # placeholder
            })

    elif domain in ('security_iam_policy',):
        from analyze_policy import analyze as analyze_policy
        from analyze_policy import analyze_inline_403
        # Try to parse as JSON input
        try:
            policy_data = json.loads(text)
            result = analyze_policy(policy_data)
        except json.JSONDecodeError:
            # If not JSON, do inline 403 analysis from error text
            result = analyze_inline_403(text)

    elif domain in ('lifecycle_cost',):
        from analyze_cost import analyze as analyze_cost
        try:
            cost_data = json.loads(text)
        except json.JSONDecodeError:
            cost_data = {
                "storage_price_per_gb": {"STANDARD": 0.023, "STANDARD_IA": 0.0125},
                "prefixes": [],
                "note": "Could not parse JSON. Provide inventory data JSON.",
            }
        result = analyze_cost(cost_data)

    elif domain in ('mount_filesystem_workspace',):
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

    elif domain in ('network_endpoint_access',):
        result = {
            "ok": True,
            "module": "network_diagnosis",
            "note": "Network diagnosis requires live network tools (dig, curl, traceroute). "
                    "Run these manually and collect output:\n"
                    "  dig <endpoint-hostname>\n"
                    "  curl -v --connect-timeout 5 https://<endpoint>\n"
                    "  mtr -r -c 10 <endpoint-hostname>",
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

    report = f"""# 诊断报告 (Diagnosis Report)

**生成时间:** Generated by StorageOps CLI v0.3
**分类:** {data.get('domain', data.get('category', 'unknown'))}
**置信度:** {data.get('confidence', data.get('primary_confidence', 'N/A'))}

## 摘要

{data.get('conclusion', data.get('note', 'Analysis results below.'))}

## 诊断结论

```json
{json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000]}
```

## 修复建议

{chr(10).join('- ' + r for r in data.get('recommendations', data.get('recommendation', ['See analysis for recommendations']))) if isinstance(data.get('recommendations', data.get('recommendation', [])), list) else '- ' + str(data.get('recommendations', data.get('recommendation', 'See analysis for recommendations')))}

## 后续排查清单

- [ ] Review analysis results above
- [ ] Collect additional evidence if confidence is low
- [ ] Apply recommendations (manual-only: review before executing)
- [ ] Validate fix and re-run analysis

---
*This report was auto-generated by StorageOps CLI v0.3. All conclusions should be verified.*
"""
    print(report)


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

    # Exit non-zero if any case failed
    if not result.get('passed', True):
        if isinstance(result.get('passed'), bool) and not result['passed']:
            sys.exit(1)
        elif isinstance(result.get('cases'), list):
            failed = sum(1 for c in result['cases'] if not c.get('passed', True))
            if failed > 0:
                sys.exit(1)


def _cmd_eval_regression(args):
    """Compare latest two metric snapshots and report confidence regressions."""
    metrics_file = Path(getattr(args, 'metrics_file', None) or
                        Path(__file__).parent.parent.parent /
                        "storageops-eval-metrics.json")
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
            "message": "Need at least 2 metric snapshots to compare; only 1 found.",
        }))
        return

    prev_snap = history[-2]
    curr_snap = history[-1]
    prev_conf: dict[str, float] = prev_snap.get("confidence", {})
    curr_conf: dict[str, float] = curr_snap.get("confidence", {})

    regressions = []
    improvements = []
    for case, curr in curr_conf.items():
        prev = prev_conf.get(case)
        if prev is None or prev < 0 or curr < 0:
            continue
        delta = curr - prev
        if delta < -threshold:
            regressions.append({
                "case": case,
                "prev": round(prev, 4),
                "curr": round(curr, 4),
                "delta": round(delta, 4),
            })
        elif delta > threshold:
            improvements.append({
                "case": case,
                "prev": round(prev, 4),
                "curr": round(curr, 4),
                "delta": round(delta, 4),
            })

    result = {
        "ok": True,
        "module": "eval_regression",
        "prev_ts": prev_snap.get("ts", "?"),
        "curr_ts": curr_snap.get("ts", "?"),
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


# ── Main ──────────────────────────────────────────────────────────────

def cmd_mcp(args):
    """Start the StorageOps MCP server (for Claude Desktop / MCP clients)."""
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
        output = {
            "query": query,
            "count": len(results),
            "results": results,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))

    else:  # list
        results = list_cases(domain=getattr(args, 'domain', None), limit=args.limit)
        if not results:
            print("No past cases found. Run storageops agent with --llm-provider to build memory.")
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
        stats = compute_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
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
            if event == "llm_call":
                extra = (f"  turn={ev.get('turn')} in={ev.get('input_tokens')} "
                         f"out={ev.get('output_tokens')} stop={ev.get('stop_reason')}")
            elif event == "tool_call":
                extra = f"  turn={ev.get('turn')} tool={ev.get('tool')} keys={ev.get('input_keys')}"
            elif event == "tool_result":
                status = "ok" if ev.get("ok") else f"err={ev.get('error')}"
                extra = f"  turn={ev.get('turn')} tool={ev.get('tool')} {status}"
            elif event in ("session_start", "session_end"):
                extra = (f"  domain={ev.get('domain')} outcome={ev.get('outcome')} "
                         f"turns={ev.get('turns_used')}")
            elif event == "critique_turn":
                extra = f"  turn={ev.get('turn')} confirmed={ev.get('confirmed')}"
            elif event == "memory_save":
                extra = f"  domain={ev.get('domain')} root_cause={ev.get('root_cause')}"
            print(f"  [{ts}] {event}{extra}")
        return

    # default: list
    sessions = list_sessions(limit=args.limit)
    if not sessions:
        print("No sessions found in audit log. Run storageops agent with --llm-provider first.")
        return
    for s in sessions:
        ts = s["ts"]
        sid = s["session_id"]
        domain = s["domain"]
        outcome = s["outcome"]
        turns = s["turns_used"]
        tokens = s["input_tokens"] + s["output_tokens"]
        tools = ", ".join(sorted(set(s["tools"]))) or "-"
        print(f"  [{ts}] {sid}  {domain:<30} {outcome:<20} turns={turns} tokens={tokens}")
        if getattr(args, "verbose", False):
            print(f"    provider={s['provider']}  tools={tools}")


def cmd_agent(args):
    """Run the diagnostic agent (rule-based or LLM-powered)."""
    from storageops.agent import agent_run

    # Warn if --no-redact is combined with LLM provider
    if getattr(args, 'no_redact', False):
        print(
            "WARNING: --no-redact is active. Output may contain raw credentials. "
            "Do not share or store this output without manual review.",
            file=sys.stderr,
        )

    sys.exit(agent_run(
        initial_file=args.file,
        interactive=getattr(args, 'interactive', False),
        llm_provider=getattr(args, 'llm_provider', None),
        llm_model=getattr(args, 'llm_model', None),
        llm_key=getattr(args, 'llm_key', None),
        llm_base_url=getattr(args, 'llm_base_url', None),
        max_turns=getattr(args, 'max_turns', 8),
        verbose=getattr(args, 'verbose', False),
        stream=getattr(args, 'stream', False),
        supervisor=getattr(args, 'supervisor', False),
    ))


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
    p_analyze.add_argument('domain', help='Domain: s3_protocol_compatibility, cli_sdk_behavior, '
                            'performance_throughput, mount_filesystem_workspace, '
                            'network_endpoint_access, security_iam_policy, lifecycle_cost')
    p_analyze.add_argument('file', help='Evidence file')
    p_analyze.add_argument('--subdomain', help='Specific subdomain', default=None)
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
    p_eval.add_argument('--cases-dir', default='agents/skills/storageops-eval-golden-cases/cases',
                        help='Golden cases directory')
    p_eval.add_argument('--outputs-dir', default='.', help='Diagnosis outputs directory')
    p_eval.add_argument('--case', help='Single case name')
    p_eval.add_argument('--all', action='store_true', help='Evaluate all cases')
    p_eval.add_argument('--regression', action='store_true',
                        help='Compare latest two metric snapshots; exit 1 if confidence dropped')
    p_eval.add_argument('--metrics-file', default=None,
                        help='Path to storageops-eval-metrics.json (default: project root)')
    p_eval.add_argument('--threshold', type=float, default=0.10,
                        help='Regression threshold (default: 0.10)')
    p_eval.set_defaults(func=cmd_eval)

    # agent
    p_agent = sub.add_parser(
        'agent',
        help='Run diagnostic agent (offline rule-based, or LLM-powered with --llm-provider)',
    )
    p_agent.add_argument('file', nargs='?', help='Initial evidence file')
    p_agent.add_argument('--interactive', '-i', action='store_true',
                         help='Interactive mode (rule-based only): ask follow-up questions')
    # LLM provider options
    p_agent.add_argument(
        '--llm-provider',
        choices=['anthropic', 'openai', 'openai-compatible', 'ollama'],
        help='Enable LLM-powered agent. Supported: anthropic, openai, openai-compatible, ollama',
    )
    p_agent.add_argument('--llm-model', help='LLM model name override')
    p_agent.add_argument(
        '--llm-key',
        help='LLM API key (prefer ANTHROPIC_API_KEY / STORAGEOPS_LLM_KEY env var instead)',
    )
    p_agent.add_argument('--llm-base-url', help='LLM API base URL (for openai-compatible/ollama)')
    p_agent.add_argument('--max-turns', type=int, default=8,
                         help='Maximum agent turns (default: 8)')
    p_agent.add_argument('--verbose', '-v', action='store_true',
                         help='Print tool calls and turn progress to stderr')
    p_agent.add_argument('--stream', action='store_true',
                         help='Stream LLM output to stdout as it is generated')
    p_agent.add_argument('--supervisor', action='store_true',
                         help='Use multi-agent supervisor: triage first, then route to specialist(s)')
    p_agent.set_defaults(func=cmd_agent)

    # audit
    p_audit = sub.add_parser('audit', help='Inspect agent session audit log')
    audit_sub = p_audit.add_subparsers(dest='audit_action')

    audit_list = audit_sub.add_parser('list', help='List recent agent sessions')
    audit_list.add_argument('--limit', type=int, default=20, help='Max sessions (default 20)')
    audit_list.add_argument('--verbose', '-v', action='store_true',
                            help='Show provider and tools per session')

    audit_show = audit_sub.add_parser('show', help='Show full timeline for one session')
    audit_show.add_argument('session_id', help='Session ID (from audit list output)')

    audit_sub.add_parser('stats', help='Aggregate token usage, tool frequency, success rate')

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
