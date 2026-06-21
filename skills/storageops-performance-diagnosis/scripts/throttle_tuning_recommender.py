#!/usr/bin/env python3
"""Turn an observed throttle rate into concrete, safe tuning.

Deterministically maps an observed throttle rate and current concurrency to a
recommended concurrency, exponential-backoff schedule (base/max with full
jitter), and an expected post-tuning throttle rate. All outputs are explainable
arithmetic -- no model, no randomness, no currency. Emits a single JSON object.

On any bad/empty input it emits {"ok": false, ...} instead of raising.
"""

import argparse
import json
import math
import re
import sys
from typing import Any, Dict, List, Optional

# Target throttle rate we tune toward (1%). Service-side throttling scales
# roughly with offered request rate, so halving concurrency roughly halves the
# throttle rate; we reduce concurrency proportionally to hit the target.
_TARGET_RATE = 0.01
_MIN_CONCURRENCY = 1
_BACKOFF_MAX_MS = 30000  # 30s ceiling is a widely safe cap for retry schedules

_PROVIDER_HINTS = {
    "aws": "AWS S3 scales request rate per prefix; spread keys across more "
           "prefixes to raise the aggregate per-bucket limit.",
    "bos": "Baidu BOS enforces per-bucket QPS limits; spread load across "
           "prefixes and confirm the account QPS quota with the provider.",
    "oss": "Alibaba OSS applies per-bucket and per-prefix QPS limits; "
           "randomize key prefixes and check the bucket QPS quota.",
    "cos": "Tencent COS enforces per-bucket QPS limits; distribute keys "
           "across prefixes and verify the bucket QPS quota.",
}
_GENERIC_HINT = ("Most providers throttle per prefix and per bucket; "
                 "distribute keys across prefixes and confirm the account "
                 "request-rate quota with the provider.")


def parse_rate(value: str) -> float:
    """Parse a fraction (0-1), a percentage ('5%'), or 'X/Y' into a fraction."""
    if value is None:
        raise ValueError("rate is required")
    text = str(value).strip()
    if not text:
        raise ValueError("rate is empty")
    if "/" in text:
        num_s, den_s = text.split("/", 1)
        num, den = float(num_s.strip()), float(den_s.strip())
        if den <= 0:
            raise ValueError("rate denominator must be > 0")
        rate = num / den
    elif text.endswith("%"):
        rate = float(text[:-1].strip()) / 100.0
    else:
        rate = float(text)
    if rate < 0 or rate > 1:
        raise ValueError("rate must resolve to a fraction in [0, 1]")
    return rate


def parse_size(value: Optional[str]) -> Optional[int]:
    """Parse a byte count or human size like '64MB', '1.5 GiB' into bytes."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([kKmMgGtT]?)([iI]?)[bB]?\s*", text)
    if not m:
        raise ValueError(f"unparseable size: {value!r}")
    num = float(m.group(1))
    unit = m.group(2).lower()
    binary = bool(m.group(3))  # the 'i' in MiB/GiB selects 1024, not the unit letter
    if unit == "":
        return int(num)
    factor = {"k": 1, "m": 2, "g": 3, "t": 4}[unit]
    base = 1024 if binary else 1000
    return int(num * (base ** factor))


def recommend(
    throttle_rate: float,
    concurrency: int,
    request_rate: Optional[float] = None,
    object_count: Optional[int] = None,
    avg_object_size: Optional[int] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    notes: List[str] = []

    # Scale concurrency to bring throttle rate to the target. Throttling rises
    # roughly linearly with offered concurrency, so the safe concurrency is the
    # current concurrency scaled by (target / observed).
    if throttle_rate <= _TARGET_RATE:
        safe_concurrency = concurrency
        notes.append(
            f"Observed throttle rate {throttle_rate:.3f} is already at/below the "
            f"{_TARGET_RATE:.0%} target; concurrency can stay at {concurrency}."
        )
    else:
        scaled = concurrency * (_TARGET_RATE / throttle_rate)
        safe_concurrency = max(_MIN_CONCURRENCY, int(math.floor(scaled)))
        notes.append(
            f"Throttle rate {throttle_rate:.3f} exceeds the {_TARGET_RATE:.0%} "
            f"target; reduce concurrency {concurrency} -> {safe_concurrency} "
            f"(scaled by target/observed)."
        )

    # Expected throttle rate after scaling concurrency proportionally.
    expected_throttle_rate = round(
        throttle_rate * (safe_concurrency / concurrency), 4
    )

    # Backoff base grows with how hard we are being throttled: the heavier the
    # throttling, the longer the initial wait before retry. Bounded to a sane
    # range and capped by the 30s max with full jitter.
    backoff_base_ms = int(min(2000, max(100, round(throttle_rate * 2000))))
    backoff_max_ms = _BACKOFF_MAX_MS
    if backoff_base_ms > backoff_max_ms:
        backoff_base_ms = backoff_max_ms
    notes.append(
        f"Exponential backoff: base {backoff_base_ms} ms, max {backoff_max_ms} "
        f"ms, full jitter (retry delay uniform in [0, min(max, base*2^attempt)])."
    )

    if request_rate is not None:
        notes.append(
            f"At ~{request_rate:g} req/s, the safe concurrency caps offered "
            f"load to roughly {request_rate * safe_concurrency / concurrency:.1f} "
            f"req/s after tuning."
        )
    if object_count is not None and avg_object_size is not None:
        total = object_count * avg_object_size
        notes.append(
            f"Workload ~{object_count} objects x {avg_object_size} B "
            f"= {total} B total; reducing concurrency trades peak throughput "
            f"for a lower throttle rate."
        )

    provider_key = (provider or "").strip().lower()
    provider_hint = _PROVIDER_HINTS.get(provider_key, _GENERIC_HINT)

    recommendation = (
        f"Set concurrency to {safe_concurrency} and enable exponential backoff "
        f"(base {backoff_base_ms} ms, max {backoff_max_ms} ms, full jitter) to "
        f"bring the throttle rate from {throttle_rate:.1%} toward "
        f"{expected_throttle_rate:.1%}."
    )

    return {
        "ok": True,
        "safe_concurrency": safe_concurrency,
        "backoff_base_ms": backoff_base_ms,
        "backoff_max_ms": backoff_max_ms,
        "jitter": "full",
        "expected_throttle_rate": expected_throttle_rate,
        "notes": notes,
        "recommendation": recommendation,
        "provider_prefix_limit_hint": provider_hint,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recommend safe concurrency/backoff from observed throttling"
    )
    ap.add_argument("--throttle-rate", required=True,
                    help="Observed throttle rate: fraction 0-1, 'N%%', or 'X/Y'")
    ap.add_argument("--concurrency", required=True,
                    help="Current concurrency / worker count (integer)")
    ap.add_argument("--request-rate", help="Observed request rate in req/s")
    ap.add_argument("--object-count", help="Approximate object count")
    ap.add_argument("--avg-object-size",
                    help="Average object size in bytes or human form (e.g. 64MB)")
    ap.add_argument("--provider", help="Provider hint: aws/bos/oss/cos")
    args = ap.parse_args()

    try:
        throttle_rate = parse_rate(args.throttle_rate)
        concurrency = int(str(args.concurrency).strip())
        request_rate = (
            float(args.request_rate) if args.request_rate not in (None, "") else None
        )
        object_count = (
            int(args.object_count) if args.object_count not in (None, "") else None
        )
        avg_object_size = parse_size(args.avg_object_size)
        result = recommend(
            throttle_rate=throttle_rate,
            concurrency=concurrency,
            request_rate=request_rate,
            object_count=object_count,
            avg_object_size=avg_object_size,
            provider=args.provider,
        )
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
