#!/usr/bin/env python3
"""Offline analyzer for an rclone / s5cmd / obsutil sync or copy log.

The migration skill's cost estimator covers *planning*; this covers *failure
localization*. It extracts the transfer counts and classifies errors (checksum
mismatch, access denied, not found, throttling), and flags destructive
(deleting) sync — so the agent reasons over a deterministic summary instead of
eyeballing a long log. Offline-only: parses local text, contacts nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional

# Error classes ordered by diagnostic priority.
ERROR_CLASSES = [
    ("checksum_mismatch", re.compile(r"corrupted on transfer|hash differ|checksums? differ|md5.*differ|bad digest", re.I)),
    ("size_mismatch", re.compile(r"sizes? differ|size differ", re.I)),
    ("access_denied", re.compile(r"\b403\b|AccessDenied|Forbidden|SignatureDoesNotMatch", re.I)),
    ("not_found", re.compile(r"\b404\b|NoSuchKey|not found|no such (?:file|object)", re.I)),
    ("throttle", re.compile(r"\b429\b|SlowDown|TooManyRequests|RequestLimitExceeded", re.I)),
    ("metadata", re.compile(r"metadata (?:not|was not) (?:preserved|copied)|failed to set modification time", re.I)),
]
DESTRUCTIVE = re.compile(r"--delete(?:-during|-before|-after|-excluded)?\b|\bDeleted:\s*[1-9]|\bremoving\b.*\bfile", re.I)
RCLONE_STAT = {
    "transferred": re.compile(r"^\s*Transferred:\s*([\d,]+)\s*/\s*([\d,]+)", re.M),
    "errors": re.compile(r"^\s*Errors:\s*([\d,]+)", re.M),
    "checks": re.compile(r"^\s*Checks:\s*([\d,]+)\s*/\s*([\d,]+)", re.M),
    "deleted": re.compile(r"^\s*Deleted:\s*([\d,]+)", re.M),
}

RECS = {
    "checksum_mismatch": "Likely a cross-provider ETag/checksum format difference (e.g. AWS multipart `-N` vs BOS), not real corruption. Verify with the ETag rules; consider rclone `--s3-use-multipart-etag=false` or `--ignore-checksum` after confirming the data is intact.",
    "size_mismatch": "Sizes differ — suspect truncated upload, multipart boundary, or middleware re-encoding (e.g. gzip on the wire), not random corruption.",
    "access_denied": "Credentials/permissions on one side; check the AK/SK, bucket policy, and signing region for the failing endpoint.",
    "not_found": "Source path or object missing (wrong prefix/path), or destination listing lag; re-check the path and a HEAD on a known key.",
    "throttle": "Provider rate limiting — reduce concurrency/parallelism (`--transfers`, `--checkers`) and add retry/backoff.",
    "metadata": "Custom metadata/mtime not preserved across providers; verify header limits and use the tool's metadata flags.",
}


def _int(s: str) -> int:
    return int(s.replace(",", "")) if s else 0


def analyze(text: str) -> dict:
    text = text or ""
    counts = {}
    samples = {}
    for name, rx in ERROR_CLASSES:
        hits = rx.findall(text)
        counts[name] = len(hits)
        if hits:
            m = rx.search(text)
            line = text[max(0, text.rfind("\n", 0, m.start()) + 1): text.find("\n", m.start())]
            samples[name] = " ".join(line.split())[:160]

    stats = {}
    mt = RCLONE_STAT["transferred"].search(text)
    if mt:
        stats["transferred"] = _int(mt.group(1))
    me = RCLONE_STAT["errors"].search(text)
    if me:
        stats["errors"] = _int(me.group(1))
    md = RCLONE_STAT["deleted"].search(text)
    if md:
        stats["deleted"] = _int(md.group(1))

    destructive = bool(DESTRUCTIVE.search(text))
    dominant = max((c for c in counts if counts[c] > 0), key=lambda c: counts[c], default=None)

    if dominant:
        cause = f"Dominant issue: {dominant} ({counts[dominant]} occurrence(s))."
        rec = RECS[dominant]
    elif stats.get("errors", 0) > 0:
        cause, rec = "Errors reported but no recognized category matched.", "Inspect the raw ERROR lines; share a sample for classification."
    else:
        cause, rec = "No transfer errors detected in the log.", "If data is still wrong, compare object counts and checksums post-sync."

    return {
        "ok": True,
        "stats": stats,
        "error_counts": counts,
        "destructive_sync": destructive,
        "dominant_issue": dominant,
        "likely_cause": cause,
        "recommendation": rec,
        "samples": samples,
        "warnings": (["Destructive sync detected (deletes on the destination) — confirm this is intended before re-running."] if destructive else []),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", type=Path, help="rclone/s5cmd/obsutil log file")
    ap.add_argument("--stdin", action="store_true", help="Read the log from stdin")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    text = ""
    if args.log:
        text += args.log.read_text(encoding="utf-8", errors="ignore")
    if args.stdin:
        text += sys.stdin.read()
    if not text.strip():
        ap.print_help()
        return 1

    result = analyze(text)
    if args.json:
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"dominant_issue : {result['dominant_issue']}")
        print(f"error_counts   : {result['error_counts']}")
        print(f"destructive    : {result['destructive_sync']}")
        print(f"likely_cause   : {result['likely_cause']}")
        print(f"recommendation : {result['recommendation']}")
        for w in result["warnings"]:
            print(f"WARNING        : {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
