# Summary

Category: performance_throughput
Route: storageops-performance-diagnosis
Confidence: 0.85
Root Cause Type: service_side_throttling

The s5cmd sync run at concurrency 32 is offering more request rate than the
bucket allows, so the service returns 429 SlowDown on about 5% of requests. This
is service_side_throttling driven by excessive_concurrency, not a client or
network bottleneck.

# Key Evidence

- Roughly 16 of 320 sampled requests returned 429 SlowDown (~5% throttle rate).
- Every failure carries the 429 SlowDown signal; successful requests return 200.
- The run log reports concurrency 32 at ~800 req/s offered load.
- No client CPU saturation or network errors are present, so the limit is
  service-side, scaling with the offered concurrency.

# Recommendations

1. Reduce concurrency from 32 toward ~6 so the throttle rate falls under 1%.
   Run `python3 scripts/throttle_tuning_recommender.py --throttle-rate 16/320
   --concurrency 32` to compute the exact safe concurrency deterministically.
2. Enable exponential backoff with full jitter on retries (base ~100 ms, max
   ~30000 ms). The jitter spreads retries so they do not synchronize into a new
   burst of 429 SlowDown errors.
3. Validate by re-running the sync at the lower concurrency and confirming the
   429 rate drops; raise concurrency gradually only while the throttle rate
   stays under 1%.

# Validation Steps

- Re-run with the reduced concurrency and the backoff/jitter settings, then
  recompute the throttle rate from the new log.

# What Would Falsify This

- 429 SlowDown persisting at the same rate after concurrency is reduced would
  point to a per-prefix hotspot or an account-level quota rather than offered
  concurrency.
