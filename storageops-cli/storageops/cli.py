"""
StorageOps CLI v0.4

Usage:
    storageops triage <file|-|->          # classify evidence (human-readable by default)
    storageops analyze <domain> <file|->  # run parser + analyzer pipeline
    storageops diagnose <file>            # Pi agent full diagnosis (alias: agent)
    storageops batch <file> [<file>...]   # triage multiple files at once
    storageops report <analysis-json>     # render markdown from JSON
    storageops eval [--all|--case NAME]   # golden case evaluation
    storageops memory list|search|save|export|import
    storageops audit list|show|stats
    storageops mcp                        # start MCP server
    storageops serve                      # start HTTP API server

All commands operate on offline artifacts only. No cloud connections.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# storageops/__init__.py adds storageops-core to sys.path on first import.
from signatures import auto_detect, SIGNATURES  # noqa: F401


# ── Terminal helpers ──────────────────────────────────────────────────

_IS_TTY = sys.stdout.isatty()


def _c(text: str, *codes: str) -> str:
    if not _IS_TTY:
        return text
    return "\033[" + ";".join(codes) + "m" + text + "\033[0m"


def _bold(t: str) -> str:  return _c(t, "1")
def _dim(t: str) -> str:   return _c(t, "2")
def _green(t: str) -> str: return _c(t, "32")
def _yellow(t: str) -> str: return _c(t, "33")
def _red(t: str) -> str:   return _c(t, "31")
def _cyan(t: str) -> str:  return _c(t, "36")
def _blue(t: str) -> str:  return _c(t, "34")


def _hr(width: int = 60, char: str = "─") -> str:
    return _dim(char * width)


def _err(msg: str) -> None:
    print(_red("✗ ") + msg, file=sys.stderr)


def _warn(msg: str) -> None:
    print(_yellow("⚠ ") + msg, file=sys.stderr)


def _ok(msg: str) -> None:
    print(_green("✓ ") + msg)


def _conf_color(conf: float) -> str:
    pct = f"{conf * 100:.0f}%"
    if conf >= 0.70:
        return _green(pct)
    if conf >= 0.40:
        return _yellow(pct)
    return _red(pct)


def _quality_color(q: str) -> str:
    if q == "sufficient":
        return _green(q)
    if q == "partial":
        return _yellow(q)
    return _red(q)


# ── I/O helpers ───────────────────────────────────────────────────────

def _read_input(file_arg: str) -> tuple[str, str]:
    """Return (text, label). Supports '-' for stdin."""
    if file_arg == "-":
        text = sys.stdin.read()
        return text, "<stdin>"
    path = Path(file_arg)
    if not path.exists():
        _err(f"File not found: {file_arg}")
        sys.exit(1)
    return path.read_text(encoding="utf-8", errors="replace"), str(path)


def _output(data: dict, fmt: str = "json") -> None:
    """Print dict as JSON (for --format json mode)."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ── Domain constants ──────────────────────────────────────────────────

SKILL_ROUTE_MAP: dict[str, str] = {
    "s3_protocol_compatibility": "storageops-s3-protocol-compatibility",
    "cli_sdk_behavior":          "storageops-cli-sdk-diagnosis",
    "performance_throughput":    "storageops-performance-diagnosis",
    "mount_filesystem_workspace":"storageops-mount-filesystem-workspace",
    "network_endpoint_access":   "storageops-network-endpoint-access",
    "security_iam_policy":       "storageops-security-iam-policy",
    "lifecycle_cost":            "storageops-lifecycle-cost",
    "cors_configuration":        "storageops-s3-protocol-compatibility",
    "replication_versioning":    "storageops-replication-versioning",
    "bigdata_pipeline":          "storageops-bigdata-pipeline",
}


# ── cmd_triage ────────────────────────────────────────────────────────

def cmd_triage(args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "human")
    text, label = _read_input(args.file)

    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(text)

    detections = auto_detect(text)

    primary = detections[0] if detections else {
        "domain": "unknown",
        "confidence": 0.0,
        "subdomains": [],
    }

    from storageops.agent import assess_evidence
    domain = primary["domain"]
    evidence = assess_evidence(text, domain)

    # Detect input type
    input_type = "natural_language"
    if re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}.*(?:DEBUG|ERROR|INFO)", text):
        input_type = "log_file"
    elif re.search(r"<\?xml.*<Error>", text, re.IGNORECASE | re.DOTALL):
        input_type = "error_message"
    elif re.search(r"<LifecycleConfiguration>", text, re.IGNORECASE):
        input_type = "config_file"
    elif re.search(r"access_key_id|endpoint.*https?://", text, re.IGNORECASE):
        input_type = "config_file"

    next_cmd = (
        f"storageops analyze {domain} {args.file}"
        if domain != "unknown"
        else "Provide more detailed evidence (debug logs, error messages)"
    )

    output = {
        "ok": True,
        "module": "triage",
        "input_type": input_type,
        "primary_domain": domain,
        "primary_confidence": primary["confidence"],
        "evidence_quality": evidence.get("quality", "partial"),
        "missing_required": evidence.get("missing_required", []),
        "missing_helpful": evidence.get("missing_helpful", []),
        "all_detections": detections,
        "secret_scan": {"findings_count": secret_result["count"],
                        "has_secrets": secret_result["count"] > 0},
        "recommended_next_command": next_cmd,
    }

    if fmt == "json":
        _output(output)
        return

    # Human-readable output
    _print_triage_human(output, label, args.file)


def _print_triage_human(output: dict, label: str, file_arg: str) -> None:
    print()
    print(_bold("Triage") + "  " + _dim(label))
    print(_hr())

    domain = output["primary_domain"]
    conf = output["primary_confidence"]
    quality = output["evidence_quality"]

    print(f"  Domain    {_bold(domain):<40}  {_conf_color(conf)}")
    print(f"  Quality   {_quality_color(quality)}")

    detections = output.get("all_detections", [])
    if detections:
        subs = []
        for d in detections:
            for s in d.get("subdomains", []):
                if s not in subs:
                    subs.append(s)
        if subs:
            print(f"  Signals   {_dim(', '.join(subs[:6]))}")

    if len(detections) > 1:
        others = [f"{d['domain']} ({d['confidence']*100:.0f}%)" for d in detections[1:3]]
        print(f"  Also      {_dim(', '.join(others))}")

    missing_req = output.get("missing_required", [])
    missing_hlp = output.get("missing_helpful", [])
    if missing_req:
        print()
        print(f"  {_yellow('Missing required evidence:')}")
        for m in missing_req:
            print(f"    {_red('•')} {m}")
    if missing_hlp:
        print()
        print(f"  {_dim('Helpful (optional):')} ")
        for m in missing_hlp[:3]:
            print(f"    {_dim('·')} {m}")

    sc = output.get("secret_scan", {})
    if sc.get("has_secrets"):
        print()
        print(f"  {_yellow('Secrets:')} {sc['findings_count']} secret(s) redacted")

    print()
    print(_dim("─" * 60))
    print(f"  {_cyan('→')}  {_bold(output['recommended_next_command'])}")
    print()


# ── cmd_analyze ───────────────────────────────────────────────────────

def cmd_analyze(args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "human")

    if args.no_redact:
        _warn("--no-redact: output may contain raw credentials. Review before sharing.")

    text, label = _read_input(args.file)
    domain = args.domain

    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(text)
    redacted_count = secret_result["count"]
    if redacted_count > 0 and not args.no_redact:
        text = secret_result["redacted_text"]

    from storageops.agent import run_analysis, assess_evidence
    result = run_analysis(domain, text)
    evidence = assess_evidence(text, domain)
    quality = evidence.get("quality", "partial")

    result["ok"] = True
    result["module"] = f"analyze_{domain}"
    result["redacted"] = redacted_count > 0 and not args.no_redact

    if fmt == "json":
        _output(result)
        if getattr(args, "exit_code", False):
            sys.exit(_severity_exit(result))
        return

    _print_analyze_human(result, domain, label, quality, redacted_count)

    if getattr(args, "exit_code", False):
        sys.exit(_severity_exit(result))


def _severity_exit(result: dict) -> int:
    sev = str(result.get("severity", "")).lower()
    if sev in ("critical", "high"):
        return 1
    return 0


def _print_analyze_human(
    result: dict, domain: str, label: str, quality: str, redacted: int
) -> None:
    print()
    print(_bold("Analyze") + "  " + _cyan(domain) + "  " + _dim(label))
    print(_hr())

    # Root cause / conclusion
    conclusion = (
        result.get("conclusion")
        or result.get("note")
        or result.get("summary", {}).get("root_cause_likely", "")
        or result.get("denial_source", "")
    )
    if conclusion:
        print(f"  {_bold('Finding')}   {conclusion}")

    # Key numeric findings
    summary = result.get("summary", {})
    if summary.get("corrupted_count", 0) > 0:
        print(f"  {_bold('Corrupted')}  {summary['corrupted_count']} file(s) affected")
    if summary.get("has_signature_error"):
        print(f"  {_bold('Error')}     SigV4 signature mismatch detected")
    if summary.get("has_throttling") or result.get("throttle_rate_percent", 0) > 0:
        rate = result.get("throttle_rate_percent", 0)
        print(f"  {_bold('Throttle')}  {rate:.1f}% of requests throttled")
    if result.get("denial_source"):
        print(f"  {_bold('Denial')}    {result['denial_source']}")
    if result.get("issue_count", 0) > 0:
        print(f"  {_bold('Issues')}    {result['issue_count']} issue(s) found")
    if result.get("likely_root_cause"):
        print(f"  {_bold('Root Cause')} {result['likely_root_cause']}")

    # Recommendations
    recs = result.get("recommendations") or result.get("recommendation")
    if recs:
        print()
        print(f"  {_bold('Remediation')}")
        if isinstance(recs, list):
            for r in recs[:6]:
                is_mutating = "manual-only" in str(r).lower() or re.search(
                    r'\b(put|delete|aws\s+s3|rclone)', str(r), re.IGNORECASE
                )
                bullet = _yellow("•") if is_mutating else _cyan("•")
                print(f"    {bullet} {r}")
        elif isinstance(recs, str):
            print(f"    {_cyan('•')} {recs}")
        elif isinstance(recs, dict):
            for k, v in list(recs.items())[:5]:
                print(f"    {_cyan('•')} {k}: {v}")

    if result.get("error"):
        print()
        print(f"  {_red('Error')}     {result['error']}")
        if result.get("note"):
            print(f"  {_dim('Note')}      {result['note']}")

    print()
    print(_hr())
    parts = [f"Evidence quality: {_quality_color(quality)}"]
    if redacted > 0:
        parts.append(f"{_yellow(str(redacted) + ' secret(s) redacted')}")
    print("  " + "  │  ".join(parts))
    print()


# ── cmd_batch ─────────────────────────────────────────────────────────

def cmd_batch(args: argparse.Namespace) -> None:
    """Triage multiple files and show a summary table."""
    fmt = getattr(args, "format", "human")
    files = args.files

    from secret_scanner import scan as scan_secrets
    from storageops.agent import assess_evidence

    rows = []
    for f in files:
        path = Path(f)
        if not path.exists():
            rows.append({"file": f, "error": "not found"})
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            sr = scan_secrets(text)
            detections = auto_detect(text)
            primary = detections[0] if detections else {"domain": "unknown", "confidence": 0.0}
            ev = assess_evidence(text, primary["domain"])
            rows.append({
                "file": f,
                "domain": primary["domain"],
                "confidence": primary["confidence"],
                "quality": ev.get("quality", "partial"),
                "secrets": sr["count"],
                "next": f"storageops analyze {primary['domain']} {f}",
            })
        except Exception as exc:
            rows.append({"file": f, "error": str(exc)})

    if fmt == "json":
        print(json.dumps({"ok": True, "module": "batch", "count": len(rows), "results": rows},
                         indent=2, ensure_ascii=False))
        return

    print()
    print(_bold(f"Batch Triage — {len(files)} file(s)"))
    print(_hr(70))
    fmt_row = "  {:<35} {:<32} {:>5}  {}"
    print(_dim(fmt_row.format("File", "Domain", "Conf", "Quality")))
    print(_dim("─" * 70))

    for row in rows:
        if "error" in row:
            print(f"  {_red(row['file'][:35])}  {_red(row['error'])}")
            continue
        name = Path(row["file"]).name[:34]
        domain = row["domain"][:31]
        conf = _conf_color(row["confidence"])
        quality = _quality_color(row["quality"])
        secrets = f" {_yellow('🔑')}" if row["secrets"] > 0 else ""
        print(f"  {name:<35} {domain:<32} {conf:>5}{secrets}  {quality}")

    print(_dim("─" * 70))

    output_file = getattr(args, "output", None)
    if output_file:
        lines = ["# Batch Triage Report\n"]
        for row in rows:
            if "error" not in row:
                lines.append(f"- **{row['file']}**: `{row['domain']}` ({row['confidence']:.0%})")
                lines.append(f"  - Quality: {row['quality']}")
                lines.append(f"  - Next: `{row['next']}`\n")
        Path(output_file).write_text("\n".join(lines))
        print()
        _ok(f"Report saved to {output_file}")
    else:
        print()
        print(_dim("  Tip: storageops analyze <domain> <file> to deep-dive any finding"))
    print()


# ── cmd_report ────────────────────────────────────────────────────────

def cmd_report(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.exists():
        _err(f"File not found: {args.file}")
        sys.exit(1)

    data = json.loads(path.read_text())
    domain = data.get("module", data.get("category", "unknown")).replace("analyze_", "")
    confidence = data.get("confidence", data.get("primary_confidence", "N/A"))
    conclusion = (
        data.get("conclusion")
        or data.get("note")
        or "See Key Evidence for analysis details."
    )

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
    recs = data.get("recommendations") or data.get("recommendation")
    if isinstance(recs, list):
        return "\n".join(f"- {r}" for r in recs) or "- See Key Evidence section."
    if isinstance(recs, str) and recs:
        return f"- {recs}"
    if isinstance(recs, dict):
        return "\n".join(f"- {k}: {v}" for k, v in recs.items())
    return "- See Key Evidence section."


# ── cmd_eval ──────────────────────────────────────────────────────────

def cmd_eval(args: argparse.Namespace) -> None:
    if getattr(args, "regression", False):
        _cmd_eval_regression(args)
        return

    cases_dir = Path(args.cases_dir)
    outputs_dir_raw = getattr(args, "outputs_dir", None)

    if args.case:
        if outputs_dir_raw:
            # Evaluate a pre-generated LLM output file
            from eval_runner import evaluate_case
            output_path = Path(outputs_dir_raw) / f"{args.case}.md"
            if not output_path.exists():
                _err(f"Output not found: {output_path}")
                sys.exit(1)
            output_text = output_path.read_text(encoding="utf-8", errors="replace")
            result = evaluate_case(cases_dir / args.case, output_text)
        else:
            result = _fast_eval_case(cases_dir / args.case)
    elif args.all:
        if outputs_dir_raw:
            from eval_runner import evaluate_all
            result = evaluate_all(cases_dir, Path(outputs_dir_raw))
        else:
            result = _fast_eval_all(cases_dir)
    else:
        _err("Specify --case, --all, or --regression")
        sys.exit(1)

    result["ok"] = True
    result["module"] = "eval"
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("failed", 0) > 0:
        sys.exit(1)


def _fast_eval_case(case_path: Path) -> dict:
    """Rule-based fast eval for a single golden case. No LLM/Pi required."""
    import json as _json
    expected_path = case_path / "expected.json"
    if not expected_path.exists():
        return {"case": case_path.name, "passed": False, "error": "No expected.json"}

    expected = _json.loads(expected_path.read_text(encoding="utf-8"))
    input_dir = case_path / "input"
    texts: list[str] = []
    if input_dir.exists():
        for fpath in sorted(input_dir.iterdir()):
            if fpath.is_file():
                texts.append(fpath.read_text(encoding="utf-8", errors="replace"))
    text = "\n\n".join(texts)

    detections = auto_detect(text)
    top_domain = detections[0]["domain"] if detections else None
    top_conf = detections[0]["confidence"] if detections else 0.0
    expected_category = expected.get("expected_category")
    domain_ok = top_domain == expected_category

    return {
        "case": case_path.name,
        "mode": "fast",
        "passed": domain_ok,
        "score": round(top_conf, 3),
        "expected_category": expected_category,
        "actual_category": top_domain,
        "domain_match": domain_ok,
        "all_detections": [{"domain": d["domain"], "confidence": d["confidence"]}
                           for d in detections[:3]],
    }


def _fast_eval_all(cases_dir: Path) -> dict:
    """Rule-based fast eval for all golden cases. No LLM/Pi required."""
    results = []
    for case_path in sorted(cases_dir.iterdir()):
        if case_path.is_dir():
            results.append(_fast_eval_case(case_path))

    total = len(results)
    passed_count = sum(1 for r in results if r.get("passed"))
    avg_score = round(sum(r.get("score", 0) for r in results) / total, 3) if total else 0
    return {
        "mode": "fast",
        "total_cases": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "aggregate_score": avg_score,
        "unsafe_output_detected": False,
        "cases": results,
    }


def _cmd_eval_regression(args: argparse.Namespace) -> None:
    metrics_file = Path(
        getattr(args, "metrics_file", None)
        or Path(__file__).parent.parent.parent / "storageops-eval-metrics.json"
    )
    threshold = getattr(args, "threshold", 0.10)

    if not metrics_file.exists():
        _err(f"Metrics file not found: {metrics_file}")
        sys.exit(1)

    try:
        history = json.loads(metrics_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        _err(f"Cannot read metrics: {exc}")
        sys.exit(1)

    if len(history) < 2:
        print(json.dumps({
            "ok": True, "regressions": [],
            "message": "Need at least 2 metric snapshots; only 1 found.",
        }))
        return

    prev_conf: dict[str, float] = history[-2].get("confidence", {})
    curr_conf: dict[str, float] = history[-1].get("confidence", {})
    regressions, improvements = [], []

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
        "ok": True, "module": "eval_regression",
        "prev_ts": history[-2].get("ts", "?"), "curr_ts": history[-1].get("ts", "?"),
        "threshold": threshold, "regressions": regressions,
        "improvements": improvements, "regression_count": len(regressions),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if regressions:
        print(f"\nREGRESSION: {len(regressions)} case(s) dropped confidence by >{threshold:.0%}:",
              file=sys.stderr)
        for r in regressions:
            print(f"  {r['case']}: {r['prev']:.2f} → {r['curr']:.2f} ({r['delta']:+.2f})",
                  file=sys.stderr)
        sys.exit(1)


# ── cmd_agent / cmd_diagnose ──────────────────────────────────────────

def _result_has_streamed_output(result) -> bool:
    stream_types = {"delta", "content_delta", "message_delta", "token", "text"}
    for event in getattr(result, "raw_events", []):
        typ = str(event.get("type") or event.get("event") or "").lower()
        if typ in stream_types and (
            event.get("text") or event.get("delta") or event.get("content")
        ):
            return True
    return False


def cmd_agent(args: argparse.Namespace) -> None:
    """Run the Pi Coding Agent for full offline diagnosis."""
    from storageops.runtime import AgentRunOptions, PiRpcRuntime

    fmt = getattr(args, "format", "human")
    file_arg = args.file

    if file_arg == "-":
        import tempfile
        text = sys.stdin.read()
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="storageops-stdin-"
        )
        tmp.write(text)
        tmp.close()
        file_arg = tmp.name

    if fmt == "human":
        # Pre-flight: classify for user feedback.
        # When streaming, route to stderr so stdout contains only the report.
        _pf = sys.stderr if getattr(args, "stream", False) else sys.stdout
        try:
            text = Path(file_arg).read_text(encoding="utf-8", errors="replace")
            detections = auto_detect(text)
            domain = detections[0]["domain"] if detections else "unknown"
            conf = detections[0]["confidence"] if detections else 0.0
            print(file=_pf)
            print(_bold("Diagnose") + "  " + _dim(args.file), file=_pf)
            print(_hr(), file=_pf)
            print(f"  Classifying evidence...    {_green('✓')}  "
                  f"{_bold(domain)}  ({_conf_color(conf)})", file=_pf)

            # Check memory
            from storageops.memory_store import search_cases
            keywords = " ".join([domain] + [
                s for d in detections[:2] for s in d.get("subdomains", [])
            ])
            matches = search_cases(keywords, domain=domain, top_k=2)
            if matches:
                print(f"  Memory (BM25)...           {_green('✓')}  "
                      f"{len(matches)} similar case(s) found", file=_pf)
                for m in matches[:2]:
                    print(f"    {_dim('→')} {m.get('root_cause', '?')}  "
                          f"{_dim(m.get('summary', '')[:60])}", file=_pf)
            else:
                print(f"  Memory (BM25)...           {_dim('·')}  no prior cases", file=_pf)

            print(f"  Starting Pi agent...       {_yellow('→')}  "
                  f"(max {getattr(args, 'timeout_seconds', 600)}s)", file=_pf)
            print(file=_pf)
        except Exception:
            pass  # if pre-flight fails, continue to actual agent run

    import time as _time
    from storageops.config import get_pi_command as _get_pi_cmd
    from storageops.repl import _LiveProgress

    verbose = getattr(args, "verbose", False)
    is_streaming = getattr(args, "stream", False)

    # Prefer explicit --pi-command; fall back to configured/bundled binary
    _pi_cmd_arg = getattr(args, "pi_command", None)
    _pi_cmd = _pi_cmd_arg if (_pi_cmd_arg and _pi_cmd_arg != "pi") else _get_pi_cmd()

    _progress = _LiveProgress(verbose=verbose) if not is_streaming else None

    def _event_cb(event: dict) -> None:
        if _progress:
            _progress.on_event(event)
        elif verbose:
            # streaming + verbose: print tool calls inline
            tool_name = (
                event.get("tool_name") or event.get("name")
                or (event.get("function") or {}).get("name")
                or (event.get("tool") or {}).get("name")
            )
            typ = str(event.get("type") or event.get("event") or "").lower()
            if tool_name or typ in ("tool_use", "tool_call", "function_call"):
                sys.stderr.write(f"  {_dim('›')}  {tool_name or typ}\n")
                sys.stderr.flush()

    options = AgentRunOptions(
        runtime="pi",
        stream=is_streaming,
        max_turns=getattr(args, "max_turns", 8),
        timeout_seconds=getattr(args, "timeout_seconds", 600),
        pi_command=_pi_cmd,
        pi_model=getattr(args, "pi_model", None),
        pi_provider=getattr(args, "pi_provider", None),
        verbose=verbose,
        event_callback=_event_cb,
    )

    _t0 = _time.monotonic()
    if _progress:
        _progress.__enter__()
    try:
        result = PiRpcRuntime(options).run(file_arg)
    finally:
        if _progress:
            _progress.__exit__(None, None, None)
    _elapsed = _time.monotonic() - _t0

    if result.ok:
        if fmt == "human" and not is_streaming:
            print()
            print(_hr(70))
            print(f"  {_dim(f'{_elapsed:.0f}s')}")
            print()

        if not getattr(args, "stream", False) or not _result_has_streamed_output(result):
            print(result.report_markdown)

        if getattr(args, "exit_code", False):
            # Parse severity from frontmatter
            fm_match = re.search(r"severity:\s*(\w+)", result.report_markdown or "")
            sev = fm_match.group(1).lower() if fm_match else "unknown"
            sys.exit(1 if sev in ("critical", "high") else 0)
        sys.exit(0)

    _err(result.error or "Pi runtime failed")
    if fmt == "human":
        if "Pi Coding Agent is required" in (result.error or ""):
            print()
            print("  Install and configure Pi Coding Agent, then run:")
            print(f"    storageops diagnose {args.file}")
        print()
        print("  Without Pi, use the rule-based commands:")
        print(f"    storageops triage {args.file}")
        print(f"    storageops analyze <domain> {args.file}")
    sys.exit(1)


# cmd_diagnose is the primary name; cmd_agent kept as a hidden alias
cmd_diagnose = cmd_agent


# ── cmd_resume ────────────────────────────────────────────────────────

def cmd_resume(args: argparse.Namespace) -> None:
    """Resume a past diagnostic session."""
    from storageops.session import DiagnosticSession
    from storageops.repl import run_repl

    session_id = getattr(args, "session_id", None)
    show_list  = getattr(args, "list", False)

    if session_id:
        run_repl(resume_session=session_id)
        return

    sessions = DiagnosticSession.list_sessions(limit=20)
    if not sessions:
        print()
        print("  No past sessions found.")
        print(_dim("  Start a new session with: storageops"))
        print()
        return

    # Default: resume most recent session immediately — same as `claude --continue`
    if not show_list:
        run_repl(resume_session=sessions[0]["session_id"])
        return

    # --list: show picker
    print()
    print(_bold("Recent sessions"))
    print(_hr(70))
    for i, s in enumerate(sessions, 1):
        ts     = s["ts"][:16].replace("T", " ")
        domain = (s["domain"] or "unknown").replace("_", " ")
        preview = (s["preview"] or "")[:55].replace("\n", " ")
        turns  = s["turns"]
        sid    = s["session_id"]
        has_assistant = s.get("has_assistant", False)
        mark = _green("✓") if has_assistant else _dim("·")
        print(
            f"  {_dim(f'{i}.'):<4} {mark}  {_bold(sid)}  {_dim(ts)}  "
            f"{_cyan(domain)}  {_dim(f'{turns}t')}"
        )
        if preview:
            print(f"            {_dim(preview)}")
    print()
    print(_hr(70))

    if not _IS_TTY:
        return

    try:
        choice_raw = input(f"  Resume [1–{len(sessions)}] or session ID (Enter to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not choice_raw:
        return

    try:
        idx = int(choice_raw) - 1
        if 0 <= idx < len(sessions):
            run_repl(resume_session=sessions[idx]["session_id"])
        else:
            _err(f"Invalid choice: {choice_raw}")
    except ValueError:
        run_repl(resume_session=choice_raw)


# ── cmd_config ────────────────────────────────────────────────────────

def cmd_config(args: argparse.Namespace) -> None:
    """View and modify StorageOps configuration."""
    from storageops import config as cfg_mod

    action = getattr(args, "config_action", "list") or "list"

    if action == "list":
        data = cfg_mod.load()
        print()
        print(_bold("StorageOps config"))
        print(_hr(50))
        if not data:
            print(f"  {_dim('(empty — run: storageops setup)')}")
        else:
            for k, v in data.items():
                v_display = "[REDACTED]" if "key" in k.lower() and v else str(v)
                print(f"  {_bold(k):<22}  {_dim(v_display)}")
        cfg_path = Path.home() / ".storageops" / "config.json"
        print()
        print(_dim(f"  File: {cfg_path}"))
        print()

    elif action == "get":
        key = args.key
        data = cfg_mod.load()
        if key not in data:
            _err(f"Key not found: {key}")
            sys.exit(1)
        v = data[key]
        if "key" in key.lower():
            print("[REDACTED]")
        else:
            print(v)

    elif action == "set":
        key = args.key
        value = args.value
        cfg_mod.update(**{key: value})
        _ok(f"Set {key} = {value}")


# ── cmd_update ────────────────────────────────────────────────────────

def cmd_update(args: argparse.Namespace) -> None:
    """Update Pi binary and reinstall StorageOps skills."""
    import shutil
    from storageops import pi_installer

    check_only = getattr(args, "check", False)

    print()
    print(_bold("StorageOps Update"))
    print(_hr(40))
    print()

    # Pi binary
    current = pi_installer.pi_bin_path()
    if current.exists():
        print(f"  {_dim('Pi binary:')}  {_dim(str(current))}")
    else:
        print(f"  {_yellow('!')}  Pi binary not installed — run: storageops setup")

    if not check_only:
        print(f"  {_dim('Downloading latest Pi...')}", end="", flush=True)
        try:
            def _progress(done: int, total: int) -> None:
                kb = done // 1024
                if total:
                    pct = int(done / total * 24)
                    bar = "━" * pct + "╌" * (24 - pct)
                    sys.stdout.write(f"\r  {_dim('Downloading')}  {bar}  {kb} KB")
                else:
                    sys.stdout.write(f"\r  {_dim('Downloading')}  {kb} KB")
                sys.stdout.flush()

            dest = pi_installer.download_pi(progress_cb=_progress)
            sys.stdout.write("\r\033[K")
            _ok(f"Pi updated → {_dim(str(dest))}")
        except RuntimeError as exc:
            sys.stdout.write("\r\033[K")
            print(f"  {_yellow('!')}  Pi update skipped: {exc}")

        # Reinstall skills
        bundled = _find_bundled_skills()
        if bundled:
            from storageops.config import get_workdir
            skills_dst = get_workdir() / "skills"
            if skills_dst.exists():
                shutil.rmtree(str(skills_dst))
            shutil.copytree(str(bundled), str(skills_dst))
            count = sum(1 for d in skills_dst.iterdir() if d.is_dir())
            _ok(f"{count} skills updated → {_dim(str(skills_dst))}")
        else:
            print(f"  {_dim('·')}  Skills: no bundled skills found, skipping")

    print()
    if check_only:
        print("  Run without --check to apply updates.")
    else:
        print(f"  {_green('Done.')}  Run {_bold('storageops doctor')} to verify.")
    print()


# ── cmd_scan (batch alias) ────────────────────────────────────────────

cmd_scan = cmd_batch


# ── cmd_memory ────────────────────────────────────────────────────────

def cmd_memory(args: argparse.Namespace) -> None:
    action = args.memory_action or "list"

    if action == "search":
        _cmd_memory_search(args)
    elif action == "save":
        _cmd_memory_save(args)
    elif action == "export":
        _cmd_memory_export(args)
    elif action == "import":
        _cmd_memory_import(args)
    else:
        _cmd_memory_list(args)


def _cmd_memory_list(args: argparse.Namespace) -> None:
    from storageops.memory_store import list_cases
    fmt = getattr(args, "format", "human")
    results = list_cases(
        domain=getattr(args, "domain", None),
        limit=getattr(args, "limit", 20),
    )

    if fmt == "json":
        print(json.dumps({"ok": True, "count": len(results), "cases": results},
                         indent=2, ensure_ascii=False))
        return

    if not results:
        print()
        print("  No past cases in memory.")
        print(_dim("  Run 'storageops diagnose <file>' to build memory automatically,"))
        print(_dim("  or 'storageops memory save ...' to add manually."))
        print()
        return

    print()
    print(_bold(f"Memory — {len(results)} case(s)"))
    print(_hr(70))
    for entry in results:
        ts = entry.get("ts", "")[:19].replace("T", " ")
        domain = entry.get("domain", "?")
        rc = entry.get("root_cause", "unknown")
        summary = entry.get("summary", "")[:80]
        print(f"  {_dim(ts)}  {_cyan(domain)}")
        print(f"            {_bold(rc)}")
        if summary:
            print(f"            {_dim(summary)}")
        print()


def _cmd_memory_search(args: argparse.Namespace) -> None:
    from storageops.memory_store import search_cases
    fmt = getattr(args, "format", "human")
    query = " ".join(args.query)
    results = search_cases(
        query,
        domain=getattr(args, "domain", None),
        top_k=getattr(args, "limit", 5),
    )

    if fmt == "json":
        print(json.dumps({"query": query, "count": len(results), "results": results},
                         indent=2, ensure_ascii=False))
        return

    print()
    print(_bold(f"Memory Search: '{query}'"))
    print(_hr(60))
    if not results:
        print("  No matching cases found.")
        print()
        return
    for entry in results:
        ts = entry.get("ts", "")[:10]
        domain = entry.get("domain", "?")
        rc = entry.get("root_cause", "unknown")
        summary = entry.get("summary", "")[:100]
        print(f"  {_dim(ts)}  {_cyan(domain)}  →  {_bold(rc)}")
        if summary:
            print(f"             {_dim(summary)}")
        kws = entry.get("keywords", [])
        if kws:
            print(f"             {_dim('Keywords: ' + ', '.join(kws[:6]))}")
        print()


def _cmd_memory_save(args: argparse.Namespace) -> None:
    from storageops.memory_store import save_case
    import uuid

    domain = args.domain
    root_cause = args.root_cause
    summary = args.summary
    keywords = getattr(args, "keywords", None) or []
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    session_id = f"manual-{str(uuid.uuid4())[:8]}"

    save_case(session_id, domain, root_cause, summary, keywords)
    _ok(f"Case saved  [{session_id}]  {domain}  →  {root_cause}")


def _cmd_memory_export(args: argparse.Namespace) -> None:
    from storageops.memory_store import export_cases
    output_path = getattr(args, "output", None) or "storageops-memory-export.jsonl"
    count = export_cases(output_path, domain=getattr(args, "domain", None))
    _ok(f"Exported {count} case(s) to {output_path}")


def _cmd_memory_import(args: argparse.Namespace) -> None:
    from storageops.memory_store import import_cases
    path = args.input_file
    if not Path(path).exists():
        _err(f"File not found: {path}")
        sys.exit(1)
    imported, skipped = import_cases(path, merge=getattr(args, "merge", True))
    _ok(f"Imported {imported} case(s)  ({skipped} duplicate(s) skipped)")


# ── cmd_audit ─────────────────────────────────────────────────────────

def cmd_audit(args: argparse.Namespace) -> None:
    from storageops.audit_reader import list_sessions, get_session, compute_stats

    if args.audit_action == "stats":
        stats = compute_stats()
        fmt = getattr(args, "format", "human")
        if fmt == "json":
            print(json.dumps(stats, indent=2, ensure_ascii=False))
            return
        print()
        print(_bold("Audit Stats"))
        print(_hr())
        print(f"  Sessions:      {stats.get('sessions', 0)}")
        print(f"  Domains:       {', '.join(f'{k} ({v})' for k, v in (stats.get('domains') or {}).items())}")
        print(f"  Outcomes:      {', '.join(f'{k} ({v})' for k, v in (stats.get('outcomes') or {}).items())}")
        rate = stats.get("pi_success_rate")
        if rate is not None:
            print(f"  Pi success:    {rate*100:.0f}%")
        print(f"  Redactions:    {stats.get('total_redactions', 0)}")
        tools = stats.get("tool_frequency", {})
        if tools:
            top = list(tools.items())[:5]
            print(f"  Top tools:     {', '.join(f'{t}×{c}' for t, c in top)}")
        print()
        return

    if args.audit_action == "show":
        events = get_session(args.session_id)
        if not events:
            _err(f"No events for session {args.session_id!r}")
            sys.exit(1)
        print()
        print(_bold(f"Session: {args.session_id}"))
        print(_hr())
        for ev in events:
            ts = ev.get("ts", "")[:19].replace("T", " ")
            event = ev.get("event", "?")
            extra = ""
            if event == "pi_result":
                extra = (f"  ok={ev.get('ok')} redacted={ev.get('redaction_count')} "
                         f"events={ev.get('event_count')}")
            elif event == "tool_call":
                extra = f"  [{ev.get('turn')}] {ev.get('tool')} {ev.get('input_keys', [])}"
            elif event == "tool_result":
                status = "ok" if ev.get("ok") else f"err={ev.get('error')}"
                extra = f"  [{ev.get('turn')}] {ev.get('tool')} → {status}"
            elif event in ("session_start", "session_end"):
                extra = f"  {ev.get('domain')} runtime={ev.get('runtime')} {ev.get('outcome', '')}"
            elif event == "memory_save":
                extra = f"  {ev.get('domain')} → {ev.get('root_cause')}"
            print(f"  {_dim(ts)}  {_cyan(event)}{_dim(extra)}")
        print()
        return

    # list
    sessions = list_sessions(limit=args.limit)
    fmt = getattr(args, "format", "human")
    if fmt == "json":
        print(json.dumps({"ok": True, "count": len(sessions), "sessions": sessions},
                         indent=2, ensure_ascii=False))
        return

    if not sessions:
        print()
        print("  No sessions. Run 'storageops diagnose <file>' after configuring Pi.")
        print()
        return

    print()
    print(_bold(f"Audit — {len(sessions)} session(s)"))
    print(_hr(70))
    for s in sessions:
        ts = s["ts"]
        domain = s["domain"]
        outcome = s["outcome"]
        outcome_c = _green(outcome) if outcome == "success" else _yellow(outcome)
        pi_ok = s.get("pi_ok")
        ok_mark = (_green("✓") if pi_ok else _red("✗")) if pi_ok is not None else _dim("·")
        print(f"  {_dim(ts)}  {ok_mark}  {_cyan(domain):<32} {outcome_c}")
        if getattr(args, "verbose", False):
            tools = ", ".join(sorted(set(s.get("tools", [])))) or "-"
            print(f"               tools: {_dim(tools)}")
    print()


# ── cmd_mcp / cmd_serve ───────────────────────────────────────────────

def cmd_mcp(args: argparse.Namespace) -> None:
    from storageops.mcp_server import run_mcp_server
    run_mcp_server()


def cmd_serve(args: argparse.Namespace) -> None:
    from storageops.api_server import run
    run(host=args.host, port=args.port, reload=args.reload)


# ── Setup / Doctor helpers ────────────────────────────────────────────

def _find_bundled_skills() -> Path | None:
    """Locate skills: installed package first, then repo layout fallback."""
    pkg = Path(__file__).parent / "_skills"
    if pkg.exists() and pkg.is_dir():
        return pkg
    repo = Path(__file__).resolve().parents[3] / "agents" / "skills"
    if repo.exists() and repo.is_dir():
        return repo
    return None


def cmd_setup(args: argparse.Namespace) -> None:
    """Configure StorageOps: Pi Agent, API key, skills."""
    import getpass
    import json
    import shutil
    import subprocess

    from storageops import pi_installer
    from storageops.config import (
        detect_provider_from_key, get_api_key, get_provider, update as _cfg_update,
    )

    storageops_dir = Path.home() / ".storageops"
    storageops_dir.mkdir(parents=True, exist_ok=True)

    print()
    print(_bold("StorageOps"))
    print()

    # ── Pi Agent ──────────────────────────────────────────────────────
    pi_cmd_arg = getattr(args, "pi_command", None)
    pi_path = shutil.which(pi_cmd_arg or "pi")
    pi_bin = pi_installer.pi_bin_path()

    if pi_path or pi_bin.exists():
        # Prefer stored bin path; fall back to name (not full shutil.which path)
        pi_cmd = str(pi_bin) if pi_bin.exists() else (pi_cmd_arg or "pi")
        try:
            ver = subprocess.check_output(
                [pi_path or pi_cmd, "--version"],
                text=True, stderr=subprocess.STDOUT, timeout=5,
            ).strip()
        except Exception:
            ver = ""
        detail = (ver + "  " + (pi_path or pi_cmd)).strip()
        print(f"  {_green('✓')}  Pi Agent     {_dim(detail)}")
    else:
        sys.stdout.write(f"  {_dim('·')}  Pi Agent     installing…")
        sys.stdout.flush()
        try:
            def _progress(done: int, total: int) -> None:
                if total:
                    kb = done // 1024
                    pct = int(done / total * 20)
                    sys.stdout.write(f"\r  {_dim('·')}  Pi Agent     {'━'*pct}{'╌'*(20-pct)}  {kb} KB")
                    sys.stdout.flush()

            dest = pi_installer.download_pi(progress_cb=_progress)
            added = pi_installer.ensure_path_entry()
            pi_cmd = str(dest)
            sys.stdout.write(f"\r\033[K  {_green('✓')}  Pi Agent     {_dim(pi_cmd)}\n")
            if added:
                sys.stdout.write(
                    f"     {_dim('Run: source ~/.bashrc  (or open a new shell)')}\n"
                )
        except RuntimeError as exc:
            sys.stdout.write(f"\r\033[K  {_yellow('!')}  Pi Agent     {_dim(str(exc))}\n")
            pi_cmd = pi_cmd_arg or "pi"
        sys.stdout.flush()

    # ── Skills ────────────────────────────────────────────────────────
    skills_dst = storageops_dir / "skills"
    bundled = _find_bundled_skills()
    if bundled and (not skills_dst.exists() or getattr(args, "force", False)):
        if skills_dst.exists():
            shutil.rmtree(str(skills_dst))
        shutil.copytree(str(bundled), str(skills_dst))
    if skills_dst.exists():
        count = sum(1 for d in skills_dst.iterdir() if d.is_dir())
        print(f"  {_green('✓')}  Skills       {_dim(f'{count} skills  {skills_dst}')}")
    else:
        print(f"  {_yellow('!')}  Skills       {_dim('not found — re-install storageops')}")

    # ── API key ───────────────────────────────────────────────────────
    existing_key = get_api_key()
    if existing_key:
        print(f"  {_green('✓')}  API key      {_dim(get_provider() + '  (configured)')}")
    else:
        print(f"  {_dim('·')}  API key      not configured")
        print()
        print(f"  {_dim('Anthropic:  console.anthropic.com/settings/api-keys')}")
        print(f"  {_dim('OpenAI:     platform.openai.com/api-keys')}")
        print()
        try:
            key = getpass.getpass("  API key: ").strip()
        except (EOFError, KeyboardInterrupt):
            key = ""
        if key:
            provider = detect_provider_from_key(key)
            _cfg_update(provider=provider, api_key=key)
            print(f"  {_green('✓')}  {_dim(provider + '  ·  saved')}")
        else:
            print(f"  {_yellow('!')}  No key — set ANTHROPIC_API_KEY or OPENAI_API_KEY")

    # ── Config (silent) ───────────────────────────────────────────────
    pi_settings_dir = storageops_dir / ".pi"
    pi_settings_dir.mkdir(exist_ok=True)
    (pi_settings_dir / "settings.json").write_text(
        json.dumps({"skills": ["../skills"], "enableSkillCommands": True}, indent=2) + "\n",
        encoding="utf-8",
    )
    _cfg_update(
        pi_command=pi_cmd,
        workdir=str(storageops_dir),
        skills_dir=str(skills_dst) if skills_dst.exists() else "",
    )

    print()
    print(f"  {_green('Done.')}  Run: {_bold('storageops')}")
    print()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check installation health: Python, storageops, Pi, skills, config."""
    import shutil
    import subprocess

    ok = 0
    fail = 0

    def _chk_ok(label: str, detail: str = "") -> None:
        nonlocal ok
        ok += 1
        suffix = f"  {_dim(detail)}" if detail else ""
        print(f"  {_green('✓')}  {label}{suffix}")

    def _chk_fail(label: str, hint: str = "") -> None:
        nonlocal fail
        fail += 1
        print(f"  {_red('✗')}  {label}")
        if hint:
            print(f"       {_dim(hint)}")

    print()
    print(_bold("storageops doctor"))
    print(_hr(40))
    print()

    # Python version
    _chk_ok(f"Python {sys.version.split()[0]}")

    # storageops version
    try:
        from importlib.metadata import version as _pkg_ver
        _chk_ok(f"storageops {_pkg_ver('storageops')}")
    except Exception:
        _chk_ok("storageops (version unknown)")

    # Core parser count
    try:
        from signatures import auto_detect  # noqa: F401
        _parsers_dir = Path(__file__).resolve().parents[2] / "storageops-core" / "parsers"
        if not _parsers_dir.exists():
            import storageops._parsers as _sp
            _parsers_dir = Path(_sp.__file__).parent
        n = sum(1 for f in _parsers_dir.glob("parse_*.py"))
        _chk_ok(f"storageops-core  {n} parsers")
    except Exception as exc:
        _chk_fail("storageops-core", f"error: {exc}")

    # Pi binary
    from storageops.config import get_pi_command
    pi_cmd = get_pi_command()
    pi_path = shutil.which(pi_cmd)
    if pi_path:
        try:
            ver_out = subprocess.check_output(
                [pi_cmd, "--version"], text=True, stderr=subprocess.STDOUT, timeout=5
            ).strip()
            _chk_ok(f"{pi_cmd} {ver_out}", pi_path)
        except Exception:
            _chk_ok(pi_cmd, pi_path)
    else:
        _chk_fail(f"{pi_cmd}: not found", "Install Pi Agent, then run: storageops setup")

    # Skills
    from storageops.config import get_skills_dir
    skills = get_skills_dir()
    if skills and skills.exists():
        count = sum(1 for d in skills.iterdir() if d.is_dir())
        _chk_ok(f"skills  {count} directories", str(skills))
    else:
        bundled = _find_bundled_skills()
        if bundled:
            _chk_fail("skills: not installed", "run: storageops setup")
        else:
            _chk_fail("skills: not found", "re-install storageops")

    # Config file
    cfg_file = Path.home() / ".storageops" / "config.json"
    if cfg_file.exists():
        _chk_ok("config", str(cfg_file))
    else:
        _chk_fail("config: not found", "run: storageops setup")

    # Pi settings.json
    pi_cfg = Path.home() / ".storageops" / ".pi" / "settings.json"
    if pi_cfg.exists():
        _chk_ok("pi settings", str(pi_cfg))
    else:
        _chk_fail("pi settings: not found", "run: storageops setup")

    print()
    if fail == 0:
        print(f"  {_green('All checks passed.')}  Ready to diagnose.")
    else:
        print(f"  {_yellow(str(fail) + ' issue(s) found.')}  Run {_bold('storageops setup')} to fix.")
    print()


# ── Argument parser ───────────────────────────────────────────────────

_HELP_TEXT = """\
\033[1mstorageops\033[0m — AI-powered S3 diagnostic agent

\033[1mUsage:\033[0m
  storageops                       Start interactive session
  storageops [message|@file]       Describe issue or pass a log file
  storageops < error.log           Pipe log via stdin

\033[1mFirst time:\033[0m
  storageops setup                 Download Pi Agent and configure API key

\033[1mServer mode:\033[0m
  storageops mcp                   Start MCP server (for Claude Desktop)
  storageops serve                 Start HTTP API server and web UI

Inside a session, type \033[1m/\033[0m to see all commands.
"""


def main() -> None:
    _argv = sys.argv[1:]
    _known_subcmds = {
        # CI / scripting (hidden from --help)
        "triage", "analyze", "analyse", "diagnose", "agent", "scan", "batch",
        "report", "eval", "audit",
        # Session management (hidden from --help)
        "resume",
        # Server commands
        "mcp", "serve",
        # First-time setup (shown in --help)
        "setup",
        # Compat: still routable but not advertised (use / inside session)
        "doctor", "config", "update", "memory",
        "--help", "-h", "--version",
    }
    _first = _argv[0] if _argv else None

    if _first is None:
        from storageops.repl import run_repl
        run_repl()
        return

    # Handle --version early
    if _first == "--version":
        try:
            from importlib.metadata import version as _pkg_ver
            print(f"storageops {_pkg_ver('storageops')}")
        except Exception:
            print("storageops (version unknown)")
        return

    # --help / -h: use our own clean help instead of argparse's
    if _first in ("--help", "-h"):
        print(_HELP_TEXT)
        return

    if _first not in _known_subcmds and not _first.startswith("-"):
        from storageops.repl import run_repl
        run_repl(initial_text=" ".join(_argv))
        return

    parser = argparse.ArgumentParser(
        prog="storageops",
        add_help=False,   # we handle --help ourselves above
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")

    # ════════════════════════════════════════════════════
    # Main commands
    # ════════════════════════════════════════════════════

    # ── resume (hidden: use /resume inside a session instead)
    p_resume = sub.add_parser("resume", help=argparse.SUPPRESS)
    p_resume.add_argument("session_id", nargs="?", default=None,
                          help="Session ID to resume (omit to resume most recent)")
    p_resume.add_argument("--list", action="store_true",
                          help="Show a list of recent sessions to choose from")
    p_resume.set_defaults(func=cmd_resume)

    # ── diagnose (primary name for Pi agent)
    def _add_diagnose_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("file", help="Evidence file (or '-' for stdin)")
        p.add_argument("--format", choices=["human", "json"], default="human")
        p.add_argument("--runtime", choices=["pi"], default="pi")
        p.add_argument("--pi-command", default="pi", help="Pi executable (default: pi)")
        p.add_argument("--pi-model", help="Model name passed to Pi")
        p.add_argument("--pi-provider", help="Provider name passed to Pi")
        p.add_argument("--timeout-seconds", type=int, default=600)
        p.add_argument("--max-turns", type=int, default=8)
        p.add_argument("--verbose", "-v", action="store_true")
        p.add_argument("--stream", action="store_true", help="Stream Pi output")
        p.add_argument("--exit-code", action="store_true",
                       help="Exit 1 if severity is high/critical (CI mode)")

    # diagnose: hidden — the REPL handles this use case for interactive users;
    # kept as an explicit subcommand for CI pipelines and scripting.
    p_diagnose = sub.add_parser("diagnose", help=argparse.SUPPRESS)
    _add_diagnose_args(p_diagnose)
    p_diagnose.set_defaults(func=cmd_diagnose)

    # ── config
    p_config = sub.add_parser("config", help="View and modify configuration")
    cfg_sub = p_config.add_subparsers(dest="config_action")

    cfg_sub.add_parser("list", help="Show all config keys")

    cfg_get = cfg_sub.add_parser("get", help="Get a config value")
    cfg_get.add_argument("key", help="Config key")

    cfg_set = cfg_sub.add_parser("set", help="Set a config value")
    cfg_set.add_argument("key", help="Config key")
    cfg_set.add_argument("value", help="Config value")

    p_config.set_defaults(func=cmd_config, config_action="list")

    # ── update
    p_update = sub.add_parser("update", help="Update Pi binary and skills to latest")
    p_update.add_argument("--check", action="store_true",
                          help="Check for updates without installing")
    p_update.set_defaults(func=cmd_update)

    # ── setup
    p_setup = sub.add_parser("setup", help="Download Pi and configure API key")
    p_setup.add_argument("--pi-command", default="pi", metavar="CMD",
                         help="Pi executable name or path (default: pi)")
    p_setup.set_defaults(func=cmd_setup)

    # ── doctor
    p_doctor = sub.add_parser("doctor", help="Check installation health")
    p_doctor.set_defaults(func=cmd_doctor)

    # ════════════════════════════════════════════════════
    # CI / scripting commands — hidden from main help.
    # These are the engine internals; the REPL runs them automatically.
    # Still fully functional: storageops triage/analyze/scan/report all work.
    # ════════════════════════════════════════════════════

    # ── triage
    p_triage = sub.add_parser("triage", help=argparse.SUPPRESS)
    p_triage.add_argument("file", help="Evidence file (or '-' for stdin)")
    p_triage.add_argument("--format", choices=["human", "json"], default="human")
    p_triage.set_defaults(func=cmd_triage)

    # ── analyze
    p_analyze = sub.add_parser("analyze", help=argparse.SUPPRESS)
    p_analyze.add_argument("domain", help=(
        "One of: s3_protocol_compatibility, cli_sdk_behavior, performance_throughput, "
        "mount_filesystem_workspace, network_endpoint_access, security_iam_policy, "
        "lifecycle_cost, cors_configuration, replication_versioning, bigdata_pipeline"
    ))
    p_analyze.add_argument("file", help="Evidence file (or '-' for stdin)")
    p_analyze.add_argument("--format", choices=["human", "json"], default="human")
    p_analyze.add_argument("--subdomain", default=None)
    p_analyze.add_argument("--no-redact", action="store_true")
    p_analyze.add_argument("--exit-code", action="store_true",
                           help="Exit 1 if severity is high/critical (CI mode)")
    p_analyze.add_argument("--object-size", type=float, dest="object_size")
    p_analyze.add_argument("--rtt", type=float)
    p_analyze.add_argument("--bandwidth", type=float)
    p_analyze.set_defaults(func=cmd_analyze)

    # ── scan (replaces batch)
    p_scan = sub.add_parser("scan", help=argparse.SUPPRESS)
    p_scan.add_argument("files", nargs="+", help="Evidence files")
    p_scan.add_argument("--format", choices=["human", "json"], default="human")
    p_scan.add_argument("--output", help="Save summary report to this markdown file")
    p_scan.set_defaults(func=cmd_scan)

    # ── report
    p_report = sub.add_parser("report", help=argparse.SUPPRESS)
    p_report.add_argument("file", help="Analysis JSON file")
    p_report.set_defaults(func=cmd_report)

    # ════════════════════════════════════════════════════
    # Integration / platform commands
    # ════════════════════════════════════════════════════

    # ── mcp
    p_mcp = sub.add_parser("mcp", help="Start MCP server (for Claude Desktop / MCP clients)")
    p_mcp.set_defaults(func=cmd_mcp)

    # ── serve
    p_serve = sub.add_parser("serve", help="Start HTTP API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    # ── memory
    p_memory = sub.add_parser("memory", help="Manage past diagnosed cases")
    mem_sub = p_memory.add_subparsers(dest="memory_action")

    mem_list = mem_sub.add_parser("list", help="List recent cases")
    mem_list.add_argument("--domain", help="Filter by domain")
    mem_list.add_argument("--limit", type=int, default=20)
    mem_list.add_argument("--verbose", "-v", action="store_true")
    mem_list.add_argument("--format", choices=["human", "json"], default="human")

    mem_search = mem_sub.add_parser("search", help="Search cases by keyword (BM25)")
    mem_search.add_argument("query", nargs="+", help="Search keywords")
    mem_search.add_argument("--domain", help="Filter by domain")
    mem_search.add_argument("--limit", type=int, default=5)
    mem_search.add_argument("--format", choices=["human", "json"], default="human")

    mem_save = mem_sub.add_parser("save", help="Manually save a diagnosed case")
    mem_save.add_argument("--domain", required=True)
    mem_save.add_argument("--root-cause", required=True, dest="root_cause")
    mem_save.add_argument("--summary", required=True)
    mem_save.add_argument("--keywords", help="Comma-separated keywords")

    mem_export = mem_sub.add_parser("export", help="Export memory to JSONL")
    mem_export.add_argument("--output")
    mem_export.add_argument("--domain")

    mem_import = mem_sub.add_parser("import", help="Import cases from JSONL")
    mem_import.add_argument("input_file")
    mem_import.add_argument("--no-merge", dest="merge", action="store_false")

    p_memory.set_defaults(func=cmd_memory, memory_action="list",
                          domain=None, limit=20, verbose=False, format="human")

    # ════════════════════════════════════════════════════
    # Dev / CI commands (hidden from main help)
    # ════════════════════════════════════════════════════

    # ── eval
    p_eval = sub.add_parser("eval", help=argparse.SUPPRESS)
    p_eval.add_argument("--cases-dir",
                        default="agents/skills/storageops-eval-golden-cases/cases")
    p_eval.add_argument("--outputs-dir", default=None,
                        help="Dir with pre-generated .md outputs (omit to run fast triage eval)")
    p_eval.add_argument("--case")
    p_eval.add_argument("--all", action="store_true")
    p_eval.add_argument("--regression", action="store_true")
    p_eval.add_argument("--metrics-file", default=None)
    p_eval.add_argument("--threshold", type=float, default=0.10)
    p_eval.set_defaults(func=cmd_eval)

    # ── audit
    p_audit = sub.add_parser("audit", help=argparse.SUPPRESS)
    audit_sub = p_audit.add_subparsers(dest="audit_action")
    audit_list = audit_sub.add_parser("list")
    audit_list.add_argument("--limit", type=int, default=20)
    audit_list.add_argument("--verbose", "-v", action="store_true")
    audit_list.add_argument("--format", choices=["human", "json"], default="human")
    audit_show = audit_sub.add_parser("show")
    audit_show.add_argument("session_id")
    audit_sub.add_parser("stats")
    p_audit.set_defaults(func=cmd_audit, audit_action="list", limit=20, verbose=False,
                         format="human")

    # ── agent (hidden alias for diagnose, kept for backward compat)
    p_agent = sub.add_parser("agent", help=argparse.SUPPRESS)
    _add_diagnose_args(p_agent)
    p_agent.set_defaults(func=cmd_agent)

    # ── batch (hidden alias for scan)
    p_batch = sub.add_parser("batch", help=argparse.SUPPRESS)
    p_batch.add_argument("files", nargs="+")
    p_batch.add_argument("--format", choices=["human", "json"], default="human")
    p_batch.add_argument("--output")
    p_batch.set_defaults(func=cmd_batch)

    # ── analyse (British spelling alias)
    p_analyse = sub.add_parser("analyse", help=argparse.SUPPRESS)
    p_analyse.add_argument("domain")
    p_analyse.add_argument("file")
    p_analyse.add_argument("--format", choices=["human", "json"], default="human")
    p_analyse.add_argument("--subdomain", default=None)
    p_analyse.add_argument("--no-redact", action="store_true")
    p_analyse.add_argument("--exit-code", action="store_true")
    p_analyse.add_argument("--object-size", type=float, dest="object_size")
    p_analyse.add_argument("--rtt", type=float)
    p_analyse.add_argument("--bandwidth", type=float)
    p_analyse.set_defaults(func=cmd_analyze)

    args = parser.parse_args(_argv)

    if getattr(args, "version", False):
        try:
            from importlib.metadata import version as _pkg_ver
            print(f"storageops {_pkg_ver('storageops')}")
        except Exception:
            print("storageops (version unknown)")
        return

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
