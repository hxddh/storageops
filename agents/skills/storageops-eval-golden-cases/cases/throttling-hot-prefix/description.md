# Case: throttling-hot-prefix

## What this case tests
Tests performance-diagnosis skill's ability to identify prefix hotspot-induced
throttling (429/SlowDown) and distinguish it from general rate limiting.

## Scenario
A user reports 429 errors concentrated on a single prefix `/hot-data/` that
receives 80% of all GET requests. Other prefixes work normally at similar concurrency.

## Expected Diagnosis
- Category: performance_throughput
- Subcategory: upload or download with prefix_hotspot
- Root cause: prefix hotspot causing partition-level throttling
- Confidence >= 0.75
- Must identify: single prefix concentrating requests
- Must recommend: key name prefix randomization/distribution
