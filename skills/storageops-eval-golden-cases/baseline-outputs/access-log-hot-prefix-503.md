# Summary

Category: access_log_analysis
Route: storageops-access-log-analysis
Confidence: 0.86
Root Cause Type: hot_prefix_throttling
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=hot_prefix_throttling, affected_layer=request-rate

The 503 SlowDown responses are concentrated on a single key prefix. Breaking the
log down by prefix shows every throttle event falls under `events/2026/06/06/`,
where sequential date-partitioned PUTs funnel writes into one partition that hits
its per-prefix request-rate limit. Reads under `catalog/` return 200 throughout,
so this is a hot prefix, not a bucket-wide or credential problem.

# Key Evidence

- `parse_access_log.py --by-prefix 3` attributes all six 503 SlowDown responses to
  the `events/2026/` prefix; `catalog/` has zero throttles.
- The throttled requests are PUTs with sequential keys (`a1`..`a7`) under one date
  partition — the classic hot-prefix write pattern.
- Status codes are 503 with the SlowDown error code, i.e. server-side request-rate
  throttling rather than 4xx authorization failures.
- The single requester `user/ingest` drives the throttled prefix while a different
  requester reads `catalog/` without error.

# Remediation

- Spread the keys across more prefixes so writes no longer concentrate on one
  partition — prepend a short hash or random prefix before the date instead of a
  monotonically increasing date prefix.
- Add exponential backoff with full jitter on 503/SlowDown and cap client
  concurrency; the performance-diagnosis skill's throttle_tuning_recommender.py
  converts the observed throttle rate into a concrete concurrency and backoff base.
- Re-pull the access log after the change and re-run `--by-prefix` to confirm the
  503 rate on the events prefix has dropped. Do not simply retry harder against the
  same prefix.
