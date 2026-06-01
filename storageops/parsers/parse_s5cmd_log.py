"""
Parse s5cmd --log debug output into structured operation records.

Extracts operation timing, error distribution, concurrency, and throttling events.

Usage:
    cat s5cmd.log | python -m storageops-core.parsers.parse_s5cmd_log
    python -m storageops-core.parsers.parse_s5cmd_log s5cmd.log
"""
import re
import sys
import json
from pathlib import Path

PATTERNS = {
    'operation': re.compile(
        r'(\S+)\s+(\w+)\s+(s3://\S+)\s+(?:->\s+)?(\S+)?',
    ),
    'timing': re.compile(
        r'(?:completed|finished).*?(\d+(?:\.\d+)?)\s*(s|ms|seconds?)',
        re.IGNORECASE
    ),
    'error': re.compile(
        r'(?:ERROR|ERR|error|fail).*?(\d{3})\s+(\w+)',
        re.IGNORECASE
    ),
    'http_status': re.compile(
        r'HTTP/\d\.\d\s+(\d{3})'
    ),
    'config': re.compile(
        r'(?:concurrency|numworkers|part.size|part_size)\s*[:=]\s*(\d+)',
        re.IGNORECASE
    ),
    'throughput': re.compile(
        r'(\d+(?:\.\d+)?)\s*(MB/s|MiB/s|GB/s|GiB/s)',
        re.IGNORECASE
    ),
}


def parse(text: str) -> dict:
    """Parse s5cmd debug log."""
    errors = []
    status_codes = {}
    timing_samples = []
    config = {}
    throughputs = []

    # Extract error status codes
    for m in PATTERNS['http_status'].finditer(text):
        code = int(m.group(1))
        status_codes[code] = status_codes.get(code, 0) + 1

    for m in PATTERNS['error'].finditer(text):
        errors.append({
            "status_code": int(m.group(1)),
            "error_code": m.group(2),
        })

    # Extract timing
    for m in PATTERNS['timing'].finditer(text):
        val = float(m.group(1))
        unit = m.group(2).lower()
        if unit in ('s', 'seconds', 'second'):
            val = val
        elif unit in ('ms',):
            val = val / 1000
        timing_samples.append(val)

    # Extract config
    for m in PATTERNS['config'].finditer(text):
        key = m.group(0).split('=')[0].split(':')[0].strip()
        config[key] = int(m.group(1))

    # Extract throughput
    for m in PATTERNS['throughput'].finditer(text):
        throughputs.append({
            "value": float(m.group(1)),
            "unit": m.group(2),
        })

    # Compute statistics
    total_ops = sum(status_codes.values())
    error_rate = (status_codes.get(429, 0) + sum(v for k, v in status_codes.items()
                                                  if k >= 500)) / total_ops if total_ops > 0 else 0

    return {
        "status_codes": status_codes,
        "errors": errors,
        "timing_samples": timing_samples,
        "timing_summary": {
            "count": len(timing_samples),
            "min": min(timing_samples) if timing_samples else None,
            "max": max(timing_samples) if timing_samples else None,
            "avg": sum(timing_samples) / len(timing_samples) if timing_samples else None,
        } if timing_samples else {},
        "config": config,
        "throughputs": throughputs,
        "summary": {
            "total_operations": total_ops,
            "error_rate": round(error_rate, 4),
            "has_throttling": status_codes.get(429, 0) > 0,
            "has_server_errors": any(k >= 500 for k in status_codes),
            "throttle_percentage": round(
                (status_codes.get(429, 0) / total_ops * 100), 1
            ) if total_ops > 0 else 0,
        },
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        text = path.read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()

    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_s5cmd_log"
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
