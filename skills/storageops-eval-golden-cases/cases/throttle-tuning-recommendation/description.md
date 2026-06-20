# Case: throttle-tuning-recommendation

## What this case tests
Tests the performance-diagnosis skill's ability to turn an observed service-side
throttle rate into a concrete, safe concurrency + backoff recommendation (not
just "you are being throttled").

## Scenario
A user is running `s5cmd sync` at concurrency 32 and sees roughly 5% of requests
fail with `429 SlowDown`. They ask: what concurrency and backoff should I use?

## Expected Diagnosis
- Category: performance_throughput
- Root cause: service-side throttling driven by excessive concurrency
- Confidence >= 0.8
- Must recommend: a reduced concurrency plus exponential backoff with jitter
- Must NOT recommend: any destructive or credential-leaking action
