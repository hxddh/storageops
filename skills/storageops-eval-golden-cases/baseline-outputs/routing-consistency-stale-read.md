# Routing
Category: consistency_integrity
Route: storageops-data-consistency
Confidence: 0.82
Root Cause Type: cdn_cache_stale

An old object served while the origin has the new one (ETag differs) is a cache
layer, so this routes to data-consistency: check the CDN cache and invalidate.

# Evidence Gaps
- Need a direct GET to the origin (bypassing CDN) plus the ETag and Cache-Control to
  confirm the staleness is in the cache, then invalidate.
