# Cache Layers

## When to read
Use when users report stale reads, outdated browser content, or mount/SDK views that disagree.

## Layers to check
- Application memory cache.
- SDK retry/cache behavior.
- FUSE/VFS cache.
- CDN/edge cache.
- Proxy cache.
- Local filesystem sync cache.

## Rule of thumb
Modern object stores are generally strongly consistent for PUT/DELETE. First prove which cache layer served the stale object before blaming storage consistency.
