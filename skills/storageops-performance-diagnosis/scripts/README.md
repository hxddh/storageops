# Performance-diagnosis scripts

Deterministic helpers. No model calls, no randomness, JSON output only.

## `throttle_detector.py`
Scans an object-storage debug/access log for throttling signals (429, 503,
SlowDown, rate-limit keywords), correlates with request rate, and surfaces the
hottest prefixes/operations.

```
python3 scripts/throttle_detector.py --file <log>      # or pipe via stdin
```
Output: `{ok, summary, details}` where `summary` includes status_429/503 counts,
`throttle_ratio`, `onset_rate_sec`, and `top_prefixes`.

## `throttle_tuning_recommender.py`
Turns an observed throttle rate + current concurrency into a concrete, safe
tuning: a reduced concurrency that targets ~1% throttling, an exponential
backoff schedule (base/max with full jitter), and the expected post-tuning
throttle rate.

```
python3 scripts/throttle_tuning_recommender.py \
  --throttle-rate <r> --concurrency <n> [--request-rate <req/s>] \
  [--object-count <n>] [--avg-object-size 64MB] [--provider aws|bos|oss|cos]
```
`--throttle-rate` accepts a fraction (`0.05`), a percentage (`5%`), or an `X/Y`
form (`16/320`). Output: `{ok, safe_concurrency, backoff_base_ms,
backoff_max_ms, jitter, expected_throttle_rate, notes, recommendation,
provider_prefix_limit_hint}`. Invalid/empty input yields `{ok: false, error}`
rather than a traceback. The provider hint is qualitative (no currency).
