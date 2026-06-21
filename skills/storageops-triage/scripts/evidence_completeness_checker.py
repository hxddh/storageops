#!/usr/bin/env python3
"""Deterministic evidence-completeness checker for triage.

Triage Step 3 ("is there enough evidence to diagnose, or should we ask for more?")
was prose judgment. This turns it into a structural check: given a domain and the
text the user has provided, it reports which of that domain's required-evidence
items (from references/required-evidence.md) are present vs missing, and a readiness
score, so the agent asks for the *specific* missing items instead of guessing.

Detection is deterministic keyword presence — no model, no network. Provider-
agnostic. Emits a single JSON object; bad/empty input yields {"ok": false, ...}.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# domain -> list of (item label, [detection keywords/phrases]). An item counts as
# present if ANY keyword appears (case-insensitive substring) in the provided text.
# Derived from references/required-evidence.md.
REQUIRED: Dict[str, List[Tuple[str, List[str]]]] = {
    "signature_auth": [
        ("error message", ["SignatureDoesNotMatch", "error", "message"]),
        ("canonical request", ["CanonicalRequest", "canonical request"]),
        ("string to sign", ["StringToSign", "string to sign"]),
        ("endpoint/region config", ["endpoint", "region"]),
        ("tool/SDK name + version", ["version", "sdk", "rclone", "awscli", "boto"]),
        ("addressing style", ["virtual-hosted", "path-style", "path style"]),
        ("request timestamp", ["timestamp", "date", "clock"]),
    ],
    "permission_access_denied": [
        ("403 error body", ["403", "AccessDenied", "access denied", "forbidden"]),
        ("bucket/key", ["bucket", "key", "object"]),
        ("action attempted", ["s3:", "getobject", "putobject", "listbucket", "action"]),
        ("identity ARN", ["arn:", "role", "user", "iam"]),
        ("bucket policy", ["bucket policy", "policy"]),
        ("temporary credentials?", ["sts", "temporary", "session token", "assume"]),
    ],
    "s3_protocol_compatibility": [
        ("provider + compat version", ["provider", "bos", "oss", "cos", "minio", "compatib"]),
        ("request method/path", ["GET", "PUT", "POST", "HEAD", "method", "path"]),
        ("request headers", ["header", "authorization", "x-amz", "content-"]),
        ("response status/headers", ["status", "http", "response"]),
        ("response body", ["<error>", "body", "xml", "message"]),
        ("expected vs observed", ["expected", "observed", "works on aws"]),
    ],
    "cli_sdk_behavior": [
        ("tool name + version", ["version", "rclone", "s5cmd", "awscli", "boto", "mc "]),
        ("config (redacted)", ["config", "profile", ".conf", "endpoint"]),
        ("command line", ["$", "command", "cp ", "sync", "ls "]),
        ("debug/trace output", ["debug", "trace", "-vv", "--debug"]),
        ("expected vs observed", ["expected", "observed", "works with"]),
    ],
    "performance_throughput": [
        ("command/tool", ["rclone", "s5cmd", "aws s3", "command", "tool"]),
        ("object sizes/count", ["size", "objects", "files", "count", "MB", "GB"]),
        ("concurrency/part size", ["concurrency", "workers", "threads", "part size", "chunk"]),
        ("observed throughput", ["MB/s", "MiB/s", "Gbps", "throughput", "rate"]),
        ("baseline/expected", ["expected", "baseline", "should"]),
        ("throttle errors", ["429", "503", "SlowDown", "throttl"]),
    ],
    "mount_filesystem_workspace": [
        ("mount type", ["s3fs", "rclone mount", "ossfs", "bosfs", "gcsfuse", "mountpoint", "fuse"]),
        ("mount options", ["--vfs", "cache", "stat", "attr-timeout", "dir-cache", "option"]),
        ("workspace layout", ["git", "node_modules", "venv", "build", "repo", "workspace"]),
        ("timing comparison", ["slow", "local", "ssd", "seconds", "latency", "vs"]),
        ("fuse/kernel errors", ["dmesg", "fuse", "kernel", "transport endpoint"]),
    ],
    "network_endpoint_access": [
        ("endpoint/hostname", ["endpoint", "host", "https://", "url"]),
        ("DNS resolution", ["dns", "dig", "nslookup", "nxdomain", "resolve"]),
        ("access path type", ["vpc", "privatelink", "public", "subnet", "nat"]),
        ("TLS/cert", ["tls", "ssl", "certificate", "cert"]),
        ("RTT/MTU/route", ["ping", "mtr", "rtt", "mtu", "traceroute", "tracepath", "route"]),
        ("proxy/NAT config", ["proxy", "nat", "firewall"]),
    ],
    "security_iam_policy": [
        ("error + request id", ["request id", "requestid", "error", "denied"]),
        ("IAM policy JSON", ["\"effect\"", "iam", "policy", "statement"]),
        ("bucket policy JSON", ["bucket policy", "principal", "resource"]),
        ("identity type", ["role", "user", "sts", "root", "assume"]),
        ("action + resource ARN", ["s3:", "arn:", "action", "resource"]),
        ("condition keys", ["condition", "aws:sourcearn", "stringequals"]),
    ],
    "lifecycle_cost": [
        ("lifecycle config", ["lifecycle", "transition", "expiration", "rule"]),
        ("storage class", ["standard", "_ia", "glacier", "archive", "deep_archive"]),
        ("sizes/count per prefix", ["size", "objects", "count", "prefix", "KB", "MB"]),
        ("min storage duration", ["minimum", "duration", "days", "min-billable"]),
        ("access frequency", ["access", "hot", "warm", "cold", "frequency"]),
    ],
}

# Friendly aliases so callers can pass taxonomy/category names too.
ALIASES = {
    "signature": "signature_auth",
    "auth": "signature_auth",
    "access_denied": "permission_access_denied",
    "permission": "permission_access_denied",
    "protocol": "s3_protocol_compatibility",
    "cli_sdk": "cli_sdk_behavior",
    "performance": "performance_throughput",
    "mount": "mount_filesystem_workspace",
    "network": "network_endpoint_access",
    "security": "security_iam_policy",
    "iam": "security_iam_policy",
    "lifecycle": "lifecycle_cost",
    "cost": "lifecycle_cost",
}


def _resolve_domain(domain: str) -> Optional[str]:
    d = (domain or "").strip().lower()
    if d in REQUIRED:
        return d
    if d in ALIASES:
        return ALIASES[d]
    # tolerate hyphens and the storageops- prefix
    d2 = d.replace("-", "_").replace("storageops_", "")
    if d2 in REQUIRED:
        return d2
    if d2 in ALIASES:
        return ALIASES[d2]
    return None


def check(domain: str, text: str) -> Dict[str, object]:
    resolved = _resolve_domain(domain)
    if resolved is None:
        return {
            "ok": False,
            "error": f"unknown domain {domain!r}; known: {sorted(REQUIRED)}",
        }
    low = text.lower()
    present: List[str] = []
    missing: List[str] = []
    for label, keywords in REQUIRED[resolved]:
        if any(k.lower() in low for k in keywords):
            present.append(label)
        else:
            missing.append(label)
    total = len(present) + len(missing)
    readiness = round(len(present) / total, 2) if total else 0.0
    if readiness >= 0.8:
        verdict, rec = "ready", "Enough evidence to attempt a confident diagnosis."
    elif readiness >= 0.5:
        verdict = "partial"
        rec = "Diagnose tentatively, but request the missing items to raise confidence: " + "; ".join(missing)
    else:
        verdict = "insufficient"
        rec = "Do not diagnose yet — ask the user for: " + "; ".join(missing)
    return {
        "ok": True,
        "domain": resolved,
        "readiness": readiness,
        "verdict": verdict,
        "present": present,
        "missing": missing,
        "recommendation": rec,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Check triage evidence completeness for a domain")
    ap.add_argument("--domain", required=True, help=f"one of {sorted(REQUIRED)} (aliases ok)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--text", help="provided evidence text")
    src.add_argument("--file", type=Path, help="file with the provided evidence text")
    src.add_argument("--stdin", action="store_true", help="read evidence text from stdin")
    args = ap.parse_args(argv)

    try:
        if args.stdin:
            text = sys.stdin.read()
        elif args.file:
            text = args.file.read_text(encoding="utf-8")
        else:
            text = args.text or ""
    except OSError as exc:
        print(json.dumps({"ok": False, "error": f"could not read input: {exc}"}, indent=2))
        return 0

    print(json.dumps(check(args.domain, text), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
