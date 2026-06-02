#!/usr/bin/env python3
"""Detect throttling patterns in object-storage debug/access logs.

Scans logs for 429, 503, SlowDown, and rate-limit signals; correlates with
request rate; identifies affected prefixes and operations. Outputs JSON
{ok, summary, details}.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

_THROTTLE_RE = re.compile(
    r"slow\s*down|rate\s+exceeded|throttl|request\s*limit|quota\s+exceeded|"
    r"too\s+many\s+requests|try\s+again|bandwidth\s+exceeded|tps\s+exceeded",
    re.IGNORECASE,
)
_TS_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)
_TS_FMTS = [
    "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
]
_STATUS_RE = re.compile(r"(?<![\d.])(429|503)(?!\d)")


def _parse_ts(line: str) -> Optional[datetime]:
    m = _TS_RE.search(line)
    if not m:
        return None
    ts = m.group(1)
    for fmt in _TS_FMTS:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _extract_path(line: str) -> Optional[str]:
    # path=... key=... object=... or /bucket/... pattern after HTTP method
    for pat in [r'(?:path|key|object|prefix)\s*[=:]\s*(\S+)',
                r'"[A-Z]+\s+(/\S+)',
                r'(/\S+)']:
        m = re.search(pat, line, re.IGNORECASE)
        if m:
            return m.group(1).rstrip(',;)}]"\'')
    return None


def _prefix(path: str, depth: int = 2) -> str:
    parts = path.strip("/").split("/")
    return "/".join(parts[:depth]) if len(parts) > 1 else path


def _extract_throttle_status(line: str) -> Optional[str]:
    for match in _STATUS_RE.finditer(line):
        context = line[max(0, match.start() - 32): match.end() + 32].lower()
        if re.search(r"status|http|error|err|fail|slowdown|throttl|rate", context):
            return match.group(1)
    return None


class ThrottleDetector:
    def __init__(self, lines: List[str]):
        self.lines = lines
        self.events: List[Dict[str, Any]] = []
        self.code_429 = self.code_503 = self.kw_hits = 0
        self.prefixes: Counter = Counter()
        self.ops: Counter = Counter()
        self.all_ts: List[datetime] = []
        self.throttle_ts: List[datetime] = []

    def scan(self) -> None:
        for line in self.lines:
            ts = _parse_ts(line)
            if ts:
                self.all_ts.append(ts)

            code = _extract_throttle_status(line)
            if code:
                if code == "429":
                    self.code_429 += 1
                else:
                    self.code_503 += 1

            kw = _THROTTLE_RE.search(line)
            if kw:
                self.kw_hits += 1

            is_throttle = bool(code) or bool(kw)
            if is_throttle and ts:
                self.throttle_ts.append(ts)

            if is_throttle:
                ev: Dict[str, Any] = {"line": line.strip()[:300]}
                if code:
                    ev["code"] = code
                if kw:
                    ev["keyword"] = kw.group(0)
                if ts:
                    ev["timestamp"] = ts.isoformat()
                path = _extract_path(line)
                if path:
                    ev["path"] = path
                    self.prefixes[_prefix(path)] += 1
                op_m = re.search(r"\b(GET|PUT|POST|DELETE|HEAD|LIST|UPLOAD|COPY)\b", line)
                if op_m:
                    ev["operation"] = op_m.group(1)
                    self.ops[op_m.group(1)] += 1
                self.events.append(ev)

    def _onset_rate(self, window: float = 60.0) -> Optional[float]:
        sts = sorted(self.throttle_ts)
        if len(sts) < 2:
            return None
        best, j = 0.0, 0
        for i in range(len(sts)):
            while j < len(sts) and (sts[j] - sts[i]).total_seconds() <= window:
                j += 1
            rate = (j - i) / window
            if rate > best:
                best = rate
        return round(best, 4) if best > 0 else None

    def summary(self) -> Dict[str, Any]:
        req_rate = None
        if len(self.all_ts) >= 2:
            dur = (max(self.all_ts) - min(self.all_ts)).total_seconds()
            if dur > 0:
                req_rate = round(len(self.all_ts) / dur, 4)
        ratio = None
        if self.all_ts:
            ratio = round(len(self.throttle_ts) / len(self.all_ts), 4)
        return {
            # One throttle line is one event, even if it carries both a status
            # code and a keyword (e.g. "503 SlowDown"); summing the breakdown
            # counters would double-count such lines.
            "total_events": len(self.events),
            "status_429": self.code_429,
            "status_503": self.code_503,
            "keyword_hits": self.kw_hits,
            "request_rate_sec": req_rate,
            "throttle_ratio": ratio,
            "onset_rate_sec": self._onset_rate(),
            "top_prefixes": self.prefixes.most_common(10),
            "top_operations": self.ops.most_common(),
        }

    def to_json(self) -> str:
        return json.dumps({
            "ok": True,
            "summary": self.summary(),
            "details": self.events,
        }, indent=2, default=str)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Detect throttling patterns in object-storage access logs"
    )
    ap.add_argument("--file", "-f", help="Path to log file (default: stdin)")
    ap.add_argument("--stdin", action="store_true",
                    help="Force read stdin even when --file is given (reads both)")
    args = ap.parse_args()

    lines: List[str] = []
    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            lines.extend(fh)
    if args.stdin or not args.file:
        lines.extend(sys.stdin)

    if not lines:
        print(json.dumps({"ok": False, "error": "no input provided"}, indent=2))
        sys.exit(1)

    d = ThrottleDetector(lines)
    d.scan()
    print(d.to_json())


if __name__ == "__main__":
    main()
