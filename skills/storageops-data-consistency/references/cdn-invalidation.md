# CDN Invalidation

## When to read
Use when browser/CDN content is stale but direct object-store GET returns the new object.

## Checks
- Cache-Control and Expires headers.
- CDN TTL and invalidation status.
- URL versioning or query-string cache keys.
- Whether the test bypasses CDN and hits the origin directly.
