#!/usr/bin/env python3
"""Parse s5cmd --log debug output into structured JSON.

Extracts per-file operation timing, concurrency utilization,
error distribution by status code, and throttling events (429/SlowDown).
"""

import argparse
import json
import re
import sys
from datetime import datetime

TIMESTAMP_PREFIX_RE = re.compile(
    r'^\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?'
)
TIMESTAMP_RE = re.compile(
    r'^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)'
)
# Match "<op> <src> <dst>" started
OP_START_RE = re.compile(
    r'"?(cp|mv|rm|ls|du|sync|copy|move|delete|get|put|cat|'
    r'presign|bucket-version|bucket-location|select)\s+'
    r'(s3://[^\s"]+|[^\s"]+)\s+(s3://[^\s"]+|[^\s"]+)"?\s+started',
    re.I
)
# Match "<op> <src> <dst>" finished in <duration><unit>
OP_FINISH_RE = re.compile(
    r'"?(cp|mv|rm|ls|du|sync|copy|move|delete|get|put|cat|'
    r'presign|bucket-version|bucket-location|select)\s+'
    r'(s3://[^\s"]+|[^\s"]+)\s+(s3://[^\s"]+|[^\s"]+)"?\s+finished\s+in\s+'
    r'([\d.]+)\s*(\w+)',
    re.I
)
OP_END_RE = re.compile(
    r'finished\s+in\s+([\d.]+)\s*(\w+)'
)
# Match HTTP status codes 400-599 but not inside timestamps (.NNN)
_STATUS_CODE_PAT = r'(?<!\.)(?<!\d)(4\d{2}|5\d{2})(?!\d)'
STATUS_RE = re.compile(_STATUS_CODE_PAT)
THROTTLE_RE = re.compile(r'(429|SlowDown|slow.?down|throttl|rate.?limit)', re.I)
ERROR_RE = re.compile(r'\b(err(?:or)?|fail(?:ed)?)\b', re.I)


def parse_timestamp(line: str) -> float | None:
    m = TIMESTAMP_RE.match(line)
    if not m:
        return None
    ts_str = m.group(1)
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt).timestamp()
        except ValueError:
            continue
    return None


def guess_op(line: str) -> str | None:
    m = re.search(r'\b(cp|mv|rm|ls|du|sync|copy|move|delete|get|put|cat|'
                  r'presign|bucket-version|bucket-location|select)\b', line)
    return m.group(1) if m else None


def guess_file(line: str) -> str | None:
    m = re.search(r'(s3://[^\s"]+|[^\s"]+\.(?:csv|json|txt|parquet|gz|zip|bin|'
                  r'png|jpg|jpeg|pdf|html|xml|yaml|yml|log|tar))', line, re.I)
    return m.group(1) if m else None


def find_status(line: str) -> int | None:
    for m in STATUS_RE.finditer(line):
        context = line[max(0, m.start() - 32): m.end() + 32].lower()
        if not re.search(r"status|http|error|err|fail|slowdown|accessdenied|nosuchkey", context):
            continue
        code = int(m.group(1))
        if 400 <= code <= 599:
            return code
    return None


def op_key(op: str, src: str, dst: str) -> str:
    return f"{op.lower()} {src} {dst}"


def parse_log(lines: list[str]) -> dict:
    events: list[dict] = []
    errors: list[dict] = []
    throttles: list[dict] = []
    ops: list[dict] = []       # completed file-level timings
    in_flight: dict[str, float] = {}  # file_key -> start_ts

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        ts = parse_timestamp(line)
        op = guess_op(line)
        fname = guess_file(line)
        status = find_status(line)
        is_throttle = bool(THROTTLE_RE.search(line))
        is_error = bool(ERROR_RE.search(line))

        ev = {"line": lineno, "timestamp": ts, "operation": op, "file": fname}
        events.append(ev)

        if is_throttle:
            throttles.append(ev)
        if is_error or status:
            errors.append({**ev, "status_code": status})

        # Match started/finished for timing  ---------------------------------
        started = OP_START_RE.search(line)
        if started and ts:
            key = op_key(started.group(1), started.group(2), started.group(3))
            in_flight[key] = ts
            continue

        finished = OP_FINISH_RE.search(line)
        ended = finished or OP_END_RE.search(line)
        if ended and ts and in_flight:
            if finished:
                key = op_key(finished.group(1), finished.group(2), finished.group(3))
                start_ts = in_flight.pop(key, None)
                duration = float(finished.group(4))
                unit = finished.group(5).lower()
            else:
                key, start_ts = next(iter(in_flight.items()))
                del in_flight[key]
                duration = float(ended.group(1))
                unit = ended.group(2).lower()
            if start_ts is None:
                continue
            multiplier = {"s": 1, "ms": 0.001, "µs": 1e-6, "us": 1e-6,
                          "m": 60, "h": 3600}
            duration_sec = duration * multiplier.get(unit, 1)

            ops.append({
                "start": start_ts,
                "end": ts,
                "duration_sec": round(duration_sec, 6),
                "operation": op,
                "file": fname,
            })

    # --- Concurrency estimation ----------------------------------------------
    concurrency = 0
    if ops:
        boundaries = []
        for o in ops:
            boundaries.append((o["start"], 1))
            boundaries.append((o["end"], -1))
        boundaries.sort(key=lambda x: x[0])
        active = 0
        max_active = 0
        for _, delta in boundaries:
            active += delta
            if active > max_active:
                max_active = active
        concurrency = max_active

    # --- Error distribution by status code -----------------------------------
    status_counts: dict[int, int] = {}
    for e in errors:
        code = e.get("status_code")
        if code:
            status_counts[code] = status_counts.get(code, 0) + 1

    # --- Summary -------------------------------------------------------------
    total_lines = len(lines)
    total_ops = len(ops)
    total_errors = len(errors)
    total_throttles = len(throttles)
    avg_duration = round(sum(o["duration_sec"] for o in ops) / total_ops, 6) if total_ops else 0
    total_duration = round(sum(o["duration_sec"] for o in ops), 6)
    min_duration = round(min((o["duration_sec"] for o in ops), default=0), 6)
    max_duration = round(max((o["duration_sec"] for o in ops), default=0), 6)

    return {
        "ok": True,
        "summary": {
            "total_lines": total_lines,
            "total_operations": total_ops,
            "total_errors": total_errors,
            "total_throttles": total_throttles,
            "concurrency_peak": concurrency,
            "avg_duration_sec": avg_duration,
            "total_duration_sec": total_duration,
            "min_duration_sec": min_duration,
            "max_duration_sec": max_duration,
            "error_distribution": status_counts,
        },
        "details": {
            "operations": ops,
            "errors": errors,
            "throttling_events": throttles,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse s5cmd --log debug output")
    ap.add_argument("--file", help="Path to s5cmd debug log file")
    ap.add_argument("--stdin", action="store_true", help="Read log from stdin")
    args = ap.parse_args()

    if args.stdin:
        lines = sys.stdin.readlines()
    elif args.file:
        with open(args.file, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    else:
        ap.print_help()
        sys.exit(1)

    result = parse_log(lines)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
