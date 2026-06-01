"""CLI: analyze and report commands."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from storageops.ui.terminal import c, bold, dim, green, yellow, red, cyan, hr


def _read_input(file_arg: str) -> tuple[str, str]:
    if file_arg == "-":
        text = sys.stdin.read()
        return text, "<stdin>"
    path = Path(file_arg)
    if not path.exists():
        print(f"{red('✗')} File not found: {file_arg}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8", errors="replace"), str(path)


def _quality_color(q: str) -> str:
    if q == "sufficient": return green(q)
    if q == "partial": return yellow(q)
    return red(q)


def cmd_analyze(args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "human")

    if args.no_redact:
        print(f"{yellow('⚠')} --no-redact: output may contain raw credentials.")

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
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if getattr(args, "exit_code", False):
            sys.exit(_severity_exit(result))
        return
    _print_analyze_human(result, domain, label, quality, redacted_count)
    if getattr(args, "exit_code", False):
        sys.exit(_severity_exit(result))


def _severity_exit(result: dict) -> int:
    sev = str(result.get("severity", "")).lower()
    return 1 if sev in ("critical", "high") else 0


def _print_analyze_human(result: dict, domain: str, label: str, quality: str, redacted: int) -> None:
    print()
    print(bold("Analyze") + "  " + cyan(domain) + "  " + dim(label))
    print(hr())
    conclusion = (
        result.get("conclusion") or result.get("note")
        or result.get("summary", {}).get("root_cause_likely", "")
        or result.get("denial_source", "")
    )
    if conclusion:
        print(f"  {bold('Finding')}   {conclusion}")
    summary = result.get("summary", {})
    if summary.get("corrupted_count", 0) > 0:
        print(f"  {bold('Corrupted')}  {summary['corrupted_count']} file(s) affected")
    if summary.get("has_signature_error"):
        print(f"  {bold('Error')}     SigV4 signature mismatch detected")
    if summary.get("has_throttling") or result.get("throttle_rate_percent", 0) > 0:
        rate = result.get("throttle_rate_percent", 0)
        print(f"  {bold('Throttle')}  {rate:.1f}% of requests throttled")
    if result.get("denial_source"):
        print(f"  {bold('Denial')}    {result['denial_source']}")
    if result.get("issue_count", 0) > 0:
        print(f"  {bold('Issues')}    {result['issue_count']} issue(s) found")
    recs = result.get("recommendations") or result.get("recommendation")
    if recs:
        print()
        print(f"  {bold('Remediation')}")
        if isinstance(recs, list):
            for r in recs[:6]:
                is_mutating = "manual-only" in str(r).lower()
                bullet = yellow("•") if is_mutating else cyan("•")
                print(f"    {bullet} {r}")
        elif isinstance(recs, str):
            print(f"    {cyan('•')} {recs}")
        elif isinstance(recs, dict):
            for k, v in list(recs.items())[:5]:
                print(f"    {cyan('•')} {k}: {v}")
    if result.get("error"):
        print()
        print(f"  {red('Error')}     {result['error']}")
    print()
    print(hr())
    parts = [f"Evidence quality: {_quality_color(quality)}"]
    if redacted > 0:
        parts.append(f"{yellow(str(redacted) + ' secret(s) redacted')}")
    print("  " + "  │  ".join(parts))
    print()


def cmd_report(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.exists():
        print(f"{red('✗')} File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text())
    domain = data.get("module", data.get("category", "unknown")).replace("analyze_", "")
    confidence = data.get("confidence", data.get("primary_confidence", "N/A"))
    conclusion = (
        data.get("conclusion") or data.get("note")
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

{_format_recs(data)}

## Safety Notes

- Review all recommendations before executing.
- Label any cloud-mutating command with `# manual-only:` before running.

---
*Generated by StorageOps CLI. Verify all conclusions before acting.*
"""
    print(report)


def _format_recs(data: dict) -> str:
    recs = data.get("recommendations") or data.get("recommendation")
    if isinstance(recs, list):
        return "\n".join(f"- {r}" for r in recs) or "- See Key Evidence section."
    if isinstance(recs, str) and recs:
        return f"- {recs}"
    if isinstance(recs, dict):
        return "\n".join(f"- {k}: {v}" for k, v in recs.items())
    return "- See Key Evidence section."
