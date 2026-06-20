# Bandwidth Estimation

## When to read
Use to estimate how long a migration will take, or to explain why a transfer is far
slower than the link speed. This file is about **bytes and time only** — for money,
see `egress-cost-assumptions.md` (kept separate on purpose).

## Formula
```
estimated_seconds = total_bytes * 8 / effective_bits_per_second
estimated_hours   = estimated_seconds / 3600
```
`effective_bits_per_second` is the throughput you actually sustain, which is well
below the nominal link rate. Estimate it from a dry-run sample, not the NIC speed.

## What erodes effective throughput
1. **Small-object overhead dominates.** Each object costs a round-trip
   (request + TLS + first byte). Below ~1–10 MiB, per-request latency, not
   bandwidth, sets the rate: 10 KiB objects over a 10 Gbit/s link can run at a tiny
   fraction of the link because you are latency-bound, not bandwidth-bound. The fix
   is concurrency, not a bigger pipe.
2. **Concurrency is the main lever** for small files: effective throughput ≈
   parallel_streams × per-stream throughput, until you hit a bottleneck (provider
   request-rate limit, source IOPS, CPU/TLS, or the link). Raise parallelism until
   throughput stops improving or throttling (503/SlowDown) appears.
3. **Throttling caps it.** If the provider returns 503/SlowDown, you are over the
   request-rate ceiling; back off — see the performance skill's
   `throttle_tuning_recommender.py` for a concrete concurrency/backoff target.
4. **Multipart for large objects** lets a single large object use many parallel
   part uploads; tune part size and part concurrency together.

## Method
1. Run a representative **dry-run sample** (a real prefix with the true object-size
   mix) and measure sustained throughput and any throttling.
2. Plug that measured `effective_bits_per_second` into the formula for the full
   dataset; do not use the link's nominal rate.
3. Re-measure after changing concurrency — the relationship is non-linear once a
   bottleneck is hit.

## Caveats / verification status
- This is a planning estimate. Real runs vary with object-size distribution,
  source/destination region distance (RTT), and provider request-rate quotas;
  always validate against a sample before committing to a schedule.
