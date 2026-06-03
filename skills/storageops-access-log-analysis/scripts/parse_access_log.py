#!/usr/bin/env python3
"""
parse_access_log.py — Parse S3/BOS/OSS/COS access logs into structured JSON.

Handles 4 providers:
- S3: space-delimited, Apache CLF-like
- BOS: CSV with headers
- OSS: JSON (real-time logs) or tab-separated (legacy)
- COS: CSV with headers

Output:
  {
    "ok": true,
    "summary": "12,345 requests | 2.3% error rate | top operation: GET (89%)",
    "details": {
      "provider": "s3",
      "count": 12345,
      "error_rate": 0.023,
      "top_requester": "arn:aws:iam::123:user/alice",
      "top_operation": "REST.GET.OBJECT",
      "status_distribution": {"2xx": 12060, "3xx": 0, "4xx": 270, "5xx": 15},
      "operations": {"REST.GET.OBJECT": 10987, "REST.PUT.OBJECT": 1200, "REST.HEAD.OBJECT": 158},
      "requesters": [{"ip": "203.0.113.45", "count": 8234, "pct": 66.7}],
      "error_samples": [{"status": 403, "code": "AccessDenied", "requester": "arn:aws:iam::123:user/bob"}],
      "time_range": {"start": "2025-02-06T14:23:00Z", "end": "2025-02-06T15:23:00Z"}
    },
    "findings": ["3.2x spike in 403 errors vs baseline", "single IP (203.0.113.45) generates 67% of traffic"]
  }

Usage:
  python3 parse_access_log.py --file logs.txt --provider s3
  python3 parse_access_log.py --stdin < logs.csv --provider bos
  cat logs.json | python3 parse_access_log.py --stdin --provider oss
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import unquote


def detect_provider(first_line: str) -> str:
    """Auto-detect provider from log format."""
    if first_line.startswith("{"):
        return "oss"  # JSON = OSS real-time logs
    if first_line.startswith("["):
        return "s3"  # Bracketed timestamp = S3 CLF
    if "\t" in first_line and "oss-cn-" in first_line:
        return "oss"  # Tab-separated with OSS region
    # CSV with headers
    if "eventTime" in first_line and "eventSource" in first_line:
        return "cos"
    if "time" in first_line and "remote_ip" in first_line and "requester" in first_line:
        if "bce" in first_line.lower() or "bos" in first_line.lower():
            return "bos"
    # Fallback: try CSV header matching
    fields = first_line.split(",")
    if len(fields) > 10:
        lower = first_line.lower()
        if "accessid" in lower or "oss-cn" in lower:
            return "oss"
        if "secretid" in lower or "cos." in lower or "myqcloud" in lower:
            return "cos"
        if "user-abc" in lower or "bce-sdk" in lower:
            return "bos"
    return "unknown"


def _split_s3_line(line: str) -> List[str]:
    """Split S3 log line respecting quoted fields and bracketed timestamps."""
    # S3 format: bucketOwner bucket [time] ip requester requestId operation key uri status code bytes object total turn referer agent version
    # Fields that may be quoted: RequestURI (9), Referer (16), User-Agent (17)
    # Strategy: use regex to split on spaces outside quotes, treating [...] as one token
    tokens = []
    current = []
    in_quote = False
    in_bracket = False
    for ch in line:
        if ch == '"':
            in_quote = not in_quote
            current.append(ch)
        elif ch == '[' and not in_quote:
            in_bracket = True
            current.append(ch)
        elif ch == ']' and not in_quote:
            in_bracket = False
            current.append(ch)
        elif ch == ' ' and not in_quote and not in_bracket:
            if current:
                tokens.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append(''.join(current))
    return tokens


def parse_s3_log(lines: List[str]) -> Dict[str, Any]:
    """Parse AWS S3 Server Access Logs (space-delimited, Apache CLF-like)."""
    records = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = _split_s3_line(line)
        if len(parts) < 12:
            continue

        # Field indices: 0=bucketOwner, 1=bucket, 2=[time], 3=remoteIP,
        # 4=requester, 5=requestId, 6=operation, 7=key, 8=requestUri,
        # 9=status, 10=errorCode, 11=bytesSent, 12=objectSize, 13=totalTime, 14=turnaround
        status_str = parts[9]
        error = parts[10]
        bytes_str = parts[11]

        records.append({
            "status": int(status_str) if status_str.lstrip("-").isdigit() else 0,
            "error_code": error if error and error != "-" else None,
            "requester": parts[4],
            "operation": parts[6],
            "bytes_sent": int(bytes_str) if bytes_str.lstrip("-").isdigit() else 0,
            "key": unquote(parts[7]),
        })

    return _aggregate(records, "s3")


def parse_csv_log(lines: List[str], provider: str) -> Dict[str, Any]:
    """Parse CSV access logs (BOS, COS). First line is header."""
    if not lines:
        return _aggregate([], provider)

    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    records = []

    # Provider-specific field mapping.
    # NOTE (unverified): the BOS/COS wire formats and column names here have NOT
    # been confirmed against vendor docs, and the repo's own references disagree
    # (provider-log-formats.md describes BOS=tab / COS=JSON, while SKILL.md and
    # this parser assume CSV). Until the real formats are verified, this path
    # fails loudly when the expected columns are absent rather than emitting
    # silently-zeroed records. See provider-log-formats.md.
    mappings = {
        "bos": {"status": "http_status", "error_code": "error_code",
                "requester": "requester", "operation": "operation",
                "bytes_sent": "bytes_sent", "key": "key"},
        "cos": {"status": "resHttpCode", "error_code": "resErrorCode",
                "requester": "requester", "operation": "eventName",
                "bytes_sent": "resBytesSent", "key": "reqPath"},
    }

    m = mappings.get(provider, mappings["bos"])

    headers = set(reader.fieldnames or [])
    if m["status"] not in headers:
        return {
            "ok": False,
            "error": (
                f"{provider.upper()} log format not recognized (unverified mapping): "
                f"expected column '{m['status']}' not found. This parser's BOS/COS "
                f"column mapping is unconfirmed; do not trust partial results."
            ),
            "details": {"provider": provider, "detected_headers": sorted(headers)[:20]},
            "findings": [f"{provider.upper()} CSV mapping unverified — refusing to emit zeroed records"],
        }

    for row in reader:
        status_str = row.get(m["status"], "0")
        bytes_str = row.get(m["bytes_sent"], "0")
        error = row.get(m["error_code"], "-")

        records.append({
            "status": int(status_str) if status_str.lstrip("-").isdigit() else 0,
            "error_code": error if error and error != "-" else None,
            "requester": row.get(m["requester"], "-"),
            "operation": row.get(m["operation"], "-"),
            "bytes_sent": int(bytes_str) if bytes_str.lstrip("-").isdigit() else 0,
            "key": row.get(m["key"], "-"),
        })

    return _aggregate(records, provider)


def parse_json_log(lines: List[str]) -> Dict[str, Any]:
    """Parse OSS real-time JSON access logs."""
    records = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            records.append({
                "status": obj.get("httpStatus", 0),
                "error_code": obj.get("errorCode") if obj.get("errorCode") else None,
                "requester": obj.get("clientIp", "-"),
                "operation": obj.get("operation", "-"),
                "bytes_sent": obj.get("deltaDataSize", 0),
                "key": obj.get("object", "-"),
            })
        except json.JSONDecodeError:
            pass

    return _aggregate(records, "oss")


def parse_tab_log(lines: List[str]) -> Dict[str, Any]:
    """Parse OSS legacy tab-separated access logs."""
    records = []
    fields_order = [
        "bucket_owner", "bucket", "time", "remote_ip", "requester",
        "request_id", "operation", "key", "request_uri", "http_status",
        "error_code", "bytes_sent", "object_size", "total_time",
        "turnaround_time", "referer", "user_agent", "version_id"
    ]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        record = dict(zip(fields_order, parts))
        status_str = record.get("http_status", "0")
        bytes_str = record.get("bytes_sent", "0")
        error = record.get("error_code", "-")

        records.append({
            "status": int(status_str) if status_str.isdigit() else 0,
            "error_code": error if error and error != "-" else None,
            "requester": record.get("remote_ip", "-"),
            "operation": record.get("operation", "-"),
            "bytes_sent": int(bytes_str) if bytes_str.isdigit() else 0,
            "key": record.get("key", "-"),
        })

    return _aggregate(records, "oss")


def _aggregate(records: List[Dict], provider: str) -> Dict[str, Any]:
    """Aggregate log records into statistics."""
    if not records:
        return {
            "ok": True,
            "summary": "0 requests | no data",
            "details": {"provider": provider, "count": 0, "error_rate": 0, "error_samples": []},
            "findings": ["No log entries parsed"],
        }

    count = len(records)
    statuses = Counter()
    errors = Counter()
    operations = Counter()
    requesters = Counter()
    bytes_total = 0
    error_samples = []

    for r in records:
        status = r["status"]
        statuses[status] += 1
        if 400 <= status < 600:
            error_code = r.get("error_code") or f"HTTP{status}"
            errors[error_code] += 1
            if len(error_samples) < 10:
                error_samples.append({
                    "status": status,
                    "code": error_code,
                    "requester": r.get("requester", "-")
                })

        operations[r.get("operation", "-")] += 1
        requesters[r.get("requester", "-")] += 1
        bytes_total += r.get("bytes_sent", 0)

    # Status distribution
    s2xx = sum(v for k, v in statuses.items() if 200 <= k < 300)
    s3xx = sum(v for k, v in statuses.items() if 300 <= k < 400)
    s4xx = sum(v for k, v in statuses.items() if 400 <= k < 500)
    s5xx = sum(v for k, v in statuses.items() if 500 <= k < 600)

    error_count = s4xx + s5xx
    error_rate = error_count / count if count > 0 else 0

    top_req = requesters.most_common(5)
    top_op = operations.most_common(5)

    # Generate findings
    findings = []
    if error_rate > 0.05:
        findings.append(f"{error_rate*100:.0f}% error rate ({error_count}/{count} requests)")
    if top_req and top_req[0][1] > count * 0.5:
        findings.append(f"Single requester ({top_req[0][0]}) dominates {top_req[0][1]/count*100:.0f}% of traffic")
    if errors.get("AccessDenied", 0) > count * 0.02:
        findings.append(f"AccessDenied errors at {errors['AccessDenied']/count*100:.1f}% — possible credential issue")
    if errors.get("SlowDown", 0) > 0:
        findings.append(f"{errors['SlowDown']} SlowDown/Throttling events — check performance-diagnosis skill")
    if not findings:
        findings.append("No significant anomalies detected")

    return {
        "ok": True,
        "summary": f"{count} requests | {error_rate*100:.1f}% error rate | top op: {top_op[0][0]} ({top_op[0][1]/count*100:.0f}%)",
        "details": {
            "provider": provider,
            "count": count,
            "error_rate": round(error_rate, 4),
            "top_requester": top_req[0][0] if top_req else None,
            "top_operation": top_op[0][0] if top_op else None,
            "status_distribution": {"2xx": s2xx, "3xx": s3xx, "4xx": s4xx, "5xx": s5xx},
            "operations": dict(top_op),
            "requesters": [{"requester": r, "count": c, "pct": round(c/count*100, 1)} for r, c in top_req],
            "error_samples": error_samples[:5],
            "bytes_total": bytes_total,
        },
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse object storage access logs into structured JSON")
    parser.add_argument("--file", "-f", help="Path to log file")
    parser.add_argument("--stdin", "-s", action="store_true", help="Read from stdin")
    parser.add_argument("--provider", "-p", choices=["s3", "bos", "oss", "cos", "auto"],
                        default="auto", help="Log format provider (default: auto-detect)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    args = parser.parse_args()

    # Read input
    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    elif args.stdin:
        lines = sys.stdin.readlines()
    else:
        lines = sys.stdin.readlines()  # default to stdin

    if not lines:
        result = {
            "ok": False,
            "error": "No input provided. Pipe logs to stdin or use --file.",
        }
        indent = 2 if args.pretty else None
        print(json.dumps(result, indent=indent))
        sys.exit(1)

    # Auto-detect provider
    provider = args.provider
    if provider == "auto":
        provider = detect_provider(lines[0])
        print(f"[auto-detected provider: {provider}]", file=sys.stderr)

    if provider == "unknown":
        result = {
            "ok": False,
            "error": "Could not auto-detect provider. Use --provider s3|bos|oss|cos.",
            "first_line": lines[0].strip()[:200],
        }
        indent = 2 if args.pretty else None
        print(json.dumps(result, indent=indent))
        sys.exit(1)

    # Parse
    if provider == "s3":
        result = parse_s3_log(lines)
    elif provider in ("bos", "cos"):
        result = parse_csv_log(lines, provider)
    elif provider == "oss":
        if lines[0].strip().startswith("{"):
            result = parse_json_log(lines)
        else:
            result = parse_tab_log(lines)
    else:
        result = {"ok": False, "error": f"Unknown provider: {provider}"}

    indent = 2 if args.pretty else None
    print(json.dumps(result, indent=indent))


if __name__ == "__main__":
    main()
