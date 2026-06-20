# Access log — 503 SlowDown concentrated on one key prefix

An S3 server access log where PUTs under the `events/2026/06/06/` date prefix take
nearly all the 503 SlowDown responses, while reads under `catalog/` are clean. The
flat error rate alone looks moderate; the signal only becomes obvious when the log
is broken down by key prefix.

Expected diagnosis: a **hot prefix** — sequential, date-partitioned keys funnel
writes into a single partition that hits its per-prefix request-rate limit.
`parse_access_log.py --by-prefix 3` localizes the throttling to `events/2026/...`.
Remediation is to spread keys across more prefixes (e.g. a hash/random prefix) and
add exponential backoff with jitter; the performance-diagnosis skill tunes the
concurrency.
