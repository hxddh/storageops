# Request Throttling Diagnosis

## Throttling Response Codes

### AWS S3
- **HTTP 503 Slow Down** — "Please reduce your request rate."
- **HTTP 429 Too Many Requests** — (less common than 503).
- Response body includes `SlowDown` error code.

### S3-Compatible Providers
- May use 429, 503, or custom error codes.
- Error messages vary: "RequestRateLimitExceeded", "Rate exceeded", "Throttled".

## Throttling Mechanisms

### Account-Level Throttling
- Per-account request rate limit.
- Usually based on requests per second (RPS) per account.

### Bucket-Level Throttling
- Per-bucket throughput limit (GET and PUT separately).
- AWS S3: 3,500 PUT/COPY/POST/DELETE per second, 5,500 GET/HEAD per second per prefix (after partition split).

### Partition-Level Throttling
- Per-partition (prefix-based) request rate limit.
- Affected by key distribution (see `prefix-hotspot.md`).

### Per-IP Throttling
- Some providers rate-limit per source IP.
- Multiple clients behind NAT share the same limit.

## Diagnostic Workflow

### 1. Confirm Throttling
- Are there 429/503/SlowDown responses?
- Do requests succeed after adding delays?
- Does the error rate correlate with request rate?

### 2. Identify Throttling Scope
- All buckets or specific buckets?
- All prefixes or specific prefixes?
- All clients or specific client IPs?
- All operations or specific operations (PUT vs GET)?

### 3. Measure Throttling Threshold
- Slowly ramp up request rate.
- Record the rate at which throttling begins.
- Test different concurrency levels.
- Test at different times of day (throttling may be shared-tenant).

### 4. Compare to Documented Limits
- Check provider documentation for rate limits.
- Compare observed limit to documented limit.
- If significantly below documented limit, investigate partition hotspot.

## Mitigation Strategies

### Client-Side Rate Limiting
- Implement token bucket or leaky bucket rate limiter.
- Add exponential backoff with jitter for 429/503 responses.
- Distribute requests across time (not burst).

### Exponential Backoff
```
base_delay = 1 second
max_delay = 60 seconds
attempt = 0

on 429/503:
    delay = min(base_delay × 2^attempt + random(0, base_delay), max_delay)
    sleep(delay)
    attempt++
    retry

on success:
    attempt = 0  # reset
```

### Request Distribution
- Distribute PUT requests across key prefixes.
- Use random prefix hashing for write-heavy workloads.
- Batch small requests where possible (DeleteObjects).

### Connection Pool Tuning
- Too many connections → trigger per-IP throttling.
- Reduce concurrency if per-IP limits are being hit.

## Diagnostic Output

When throttling is detected, report:
- Error code and message.
- Rate at which throttling begins (RPS).
- Affected scope (account/bucket/prefix/IP).
- Correlation with specific operations or prefixes.
- Recommended rate limit and backoff configuration.

## Note for v0.1

Throttling analysis is based on error patterns in debug logs, not active
measurement. The diagnosis should state confidence level and note that
actual throttling thresholds can only be confirmed with provider documentation
or controlled testing.
