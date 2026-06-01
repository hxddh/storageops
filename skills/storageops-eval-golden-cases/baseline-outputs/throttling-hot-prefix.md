# Summary

Category: performance_throughput
Route: storageops-performance-diagnosis
Confidence: 0.82

SlowDown errors point to hot_prefix_throttling: request rate is concentrated on
one prefix instead of distributed across partitions.

# Key Evidence

- Error includes SlowDown and throttl signals.
- High request rate targets prefix `data/2024/01/15`.
- Retry alone may hide the symptom but not the prefix concentration.

# Remediation

Partition writes across more prefixes, reduce per-prefix rate, and use bounded
retry/backoff while the new partition layout drains traffic.
