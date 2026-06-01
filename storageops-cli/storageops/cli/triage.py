"""CLI: triage and batch commands."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from storageops.ui.terminal import c, bold, dim, green, yellow, red, cyan, hr, is_tty

from signatures import auto_detect  # noqa: F401


def _read_input(file_arg: str) -> tuple[str, str]:
    if file_arg == "-":
        text = sys.stdin.read()
        return text, "<stdin>"
    path = Path(file_arg)
    if not path.exists():
        print(f"{red('✗')} File not found: {file_arg}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8", errors="replace"), str(path)


def _conf_color(conf: float) -> str:
    pct = f"{conf * 100:.0f}%"
    if conf >= 0.70:
        return green(pct)
    if conf >= 0.40:
        return yellow(pct)
    return red(pct)


def _quality_color(q: str) -> str:
    if q == "sufficient":
        return green(q)
    if q == "partial":
        return yellow(q)
    return red(q)


def cmd_triage(args: argparse.Namespace) -> None:
    fmt = getattr(args, "format", "human")
    text, label = _read_input(args.file)

    from secret_scanner import scan as scan_secrets
    secret_result = scan_secrets(text)

    detections = auto_detect(text)
    primary = detections[0] if detections else {
        "domain": "unknown", "confidence": 0.0, "subdomains": [],
    }

    from storageops.agent import assess_evidence
    domain = primary["domain"]
    evidence = assess_evidence(text, domain)

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
        else "Provide more detailed evidence"
    )

    output = {
        "ok": True, "module": "triage", "input_type": input_type,
        "primary_domain": domain, "primary_confidence": primary["confidence"],
        "evidence_quality": evidence.get("quality", "partial"),
        "missing_required": evidence.get("missing_required", []),
        "missing_helpful": evidence.get("missing_helpful", []),
        "all_detections": detections,
        "secret_scan": {"findings_count": secret_result["count"],
                        "has_secrets": secret_result["count"] > 0},
        "recommended_next_command": next_cmd,
    }

    if fmt == "json":
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        return

    _print_triage_human(output, label, args.file)


def _print_triage_human(output: dict, label: str, file_arg: str) -> None:
    print()
    print(bold("Triage") + "  " + dim(label))
    print(hr())
    domain = output["primary_domain"]
    conf = output["primary_confidence"]
    quality = output["evidence_quality"]
    print(f"  Domain    {bold(domain):<40}  {_conf_color(conf)}")
    print(f"  Quality   {_quality_color(quality)}")
    detections = output.get("all_detections", [])
    if detections:
        subs = []
        for d in detections:
            for s in d.get("subdomains", []):
                if s not in subs:
                    subs.append(s)
        if subs:
            print(f"  Signals   {dim(', '.join(subs[:6]))}")
    if len(detections) > 1:
        others = [f"{d['domain']} ({d['confidence']*100:.0f}%)" for d in detections[1:3]]
        print(f"  Also      {dim(', '.join(others))}")
    missing_req = output.get("missing_required", [])
    if missing_req:
        print()
        print(f"  {yellow('Missing required evidence:')}")
        for m in missing_req:
            print(f"    {red('•')} {m}")
    sc = output.get("secret_scan", {})
    if sc.get("has_secrets"):
        print()
        print(f"  {yellow('Secrets:')} {sc['findings_count']} secret(s) redacted")
    print()
    print(dim("─" * 60))
    print(f"  {cyan('→')}  {bold(output['recommended_next_command'])}")
    print()


def cmd_batch(args: argparse.Namespace) -> None:
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
                "file": f, "domain": primary["domain"],
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
    print(bold(f"Batch Triage — {len(files)} file(s)"))
    print(hr(70))
    fmt_row = "  {:<35} {:<32} {:>5}  {}"
    print(dim(fmt_row.format("File", "Domain", "Conf", "Quality")))
    print(dim("─" * 70))
    for row in rows:
        if "error" in row:
            print(f"  {red(row['file'][:35])}  {red(row['error'])}")
            continue
        name = Path(row["file"]).name[:34]
        domain = row["domain"][:31]
        conf = _conf_color(row["confidence"])
        quality = _quality_color(row["quality"])
        secrets = f" {yellow('🔑')}" if row["secrets"] > 0 else ""
        print(f"  {name:<35} {domain:<32} {conf:>5}{secrets}  {quality}")
    print(dim("─" * 70))
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
        print(green("✓") + f" Report saved to {output_file}")
    else:
        print()
        print(dim("  Tip: storageops analyze <domain> <file> to deep-dive any finding"))
    print()
