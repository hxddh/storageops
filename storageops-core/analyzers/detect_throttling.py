"""
Detect throttling patterns from error distribution data.

Identifies throttle onset rate, affected scope, and correlation with
specific prefixes or operations.

Usage:
    python -m storageops-core.analyzers.detect_throttling errors.json
"""
import json
import sys
from pathlib import Path


def detect(data: dict) -> dict:
    """Detect throttling patterns."""
    status_codes = data.get('status_codes', {})
    errors = data.get('errors', [])
    total_ops = data.get('total_operations', 0) or sum(status_codes.values())
    prefix_errors = data.get('prefix_errors', {})

    # Count each error exactly once: SlowDown takes priority over generic throttle match
    slowdown_count = 0
    generic_throttle_count = 0
    for e in errors:
        e_str = str(e).lower()
        if 'slowdown' in e_str or 'slow down' in e_str:
            slowdown_count += 1
        elif any(t in e_str for t in ('throttl', 'rate limit', 'requestratelimit')):
            generic_throttle_count += 1

    status_429 = status_codes.get(429, 0) or status_codes.get('429', 0)
    throttle_indicators = {
        '429': status_429,
        'SlowDown': slowdown_count,
        'throttle_errors': generic_throttle_count,
    }

    throttle_count = sum(throttle_indicators.values())
    throttle_rate = round(throttle_count / total_ops * 100, 2) if total_ops > 0 else 0

    # Affected scope
    affected_prefixes = []
    for prefix, count in prefix_errors.items():
        if count > 0:
            affected_prefixes.append({
                "prefix": prefix,
                "error_count": count,
                "rate": round(count / total_ops * 100, 2) if total_ops > 0 else 0,
            })

    # Severity
    if throttle_rate == 0:
        severity = "none"
    elif throttle_rate < 0.1:
        severity = "negligible"
    elif throttle_rate < 1:
        severity = "low"
    elif throttle_rate < 5:
        severity = "medium"
    elif throttle_rate < 20:
        severity = "high"
    else:
        severity = "critical"

    # Root cause hypotheses
    causes = []
    if throttle_count > 0:
        causes.append("server_rate_limiting")
        if affected_prefixes:
            causes.append("prefix_hotspot")
            causes.sort(key=lambda c: 1 if c == 'prefix_hotspot' else 0)

    recommendations = []
    if "server_rate_limiting" in causes:
        recommendations.append("Implement exponential backoff with jitter.")
        recommendations.append("Reduce concurrency to below the throttling threshold.")
    if "prefix_hotspot" in causes:
        recommendations.append("Distribute writes across key prefixes (reverse timestamp, hash prefix).")
        recommendations.append("Check if requests cluster on specific prefix patterns.")

    return {
        "throttle_indicators": throttle_indicators,
        "total_throttle_count": throttle_count,
        "throttle_rate_percent": throttle_rate,
        "severity": severity,
        "affected_prefixes": affected_prefixes,
        "root_cause_hypotheses": causes,
        "recommendations": recommendations,
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        data = json.loads(path.read_text())
    else:
        data = json.loads(sys.stdin.read())

    result = detect(data)
    result["ok"] = True
    result["module"] = "detect_throttling"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
