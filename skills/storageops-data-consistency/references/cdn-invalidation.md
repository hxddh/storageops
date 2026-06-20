# CDN Invalidation

## When to read
Use when a browser/CDN serves stale content but a direct object-store GET already
returns the new object. That split — origin fresh, edge stale — localizes the
problem to a cache layer, not the object store (which is strongly consistent).

## Mental model
Once the origin GET is confirmed fresh, the staleness lives in one of: the CDN edge
cache, an intermediate/proxy cache, or the browser cache. Each is governed by
response headers (`Cache-Control`, `Expires`, `ETag`) and the CDN's own TTL, which
can override or ignore origin headers. Invalidation and cache-key design are the two
levers.

## Checks (in order)
1. **Bypass every cache and hit the origin.** If `curl -I` straight to the
   object-store endpoint returns the new `ETag`/`Last-Modified`, the object store is
   correct and the bug is downstream.
2. **Response headers.** A long `Cache-Control: max-age=...` (or `immutable`) tells
   the edge/browser to serve the cached copy for that whole window without
   revalidating. `no-cache` forces revalidation via `If-None-Match`/`ETag` on every
   request; `no-store` disables caching.
3. **CDN TTL and invalidation status.** The CDN's default/minimum TTL can exceed the
   origin `max-age`. After overwriting an object, the edge will not refetch until TTL
   expiry **or** an explicit invalidation completes (invalidations are async — check
   they finished).
4. **Cache key.** If the URL is unchanged, the edge reuses the cached entry. Stable
   URLs + content updates are the classic stale-CDN trap.

## How to confirm / fix
```bash
# Confirm origin is fresh (bypass CDN):
curl -I https://<bucket>.<endpoint>/<key>
# CloudFront invalidation (other CDNs have an equivalent purge API):
aws cloudfront create-invalidation --distribution-id <id> --paths "/path/to/object"
aws cloudfront get-invalidation --distribution-id <id> --id <invalidation-id>   # Completed?
```
**Durable fix:** use versioned/fingerprinted URLs (e.g. `app.9f2a1d.js`) or a
query-string cache key so each content change is a new key — no invalidation needed.
Reserve long `max-age` for immutable, fingerprinted assets only.

## Caveats / verification status
- `Cache-Control` semantics are HTTP-standard. CloudFront commands are AWS-verified;
  other CDNs (and provider-native CDNs for OSS/COS/BOS) have their own purge APIs and
  TTL precedence rules — verify the specific CDN's behavior before asserting a TTL.
