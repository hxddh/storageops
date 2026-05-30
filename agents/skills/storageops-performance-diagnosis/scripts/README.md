# storageops-performance-diagnosis Scripts

Future scripts for this domain (not yet implemented in v0.1):

## Planned Scripts

### `latency_breakdown.py`
Parse debug logs and compute timing breakdown:
- DNS lookup time distribution
- TCP connect time distribution
- TLS handshake time distribution
- TTFB distribution
- Transfer time distribution

Output summary statistics and identify dominant latency component.

### `throughput_analyzer.py`
Given timing data and object sizes, compute:
- Observed throughput vs theoretical maximum
- Efficiency ratio
- Bandwidth-delay product analysis
- Recommended concurrency for current RTT and bandwidth

### `throttle_detector.py`
Scan debug logs for throttling patterns:
- Count 429/503/SlowDown responses
- Detect throttle onset rate
- Correlate with request rate
- Identify affected prefixes or operations

### `multipart_profiler.py`
For a given multipart upload log:
- Part size distribution
- Part upload time distribution (P50/P95/P99)
- Retried parts
- Concurrency utilization (was the pool fully utilized?)
- Recommendations for part size and concurrency changes

## Principles

- All scripts must operate on offline log/metric files only.
- No active network measurement against live endpoints.
- Output must be structured for downstream analysis.
- Resource utilization analysis is based on logged metrics, not live system probing.
