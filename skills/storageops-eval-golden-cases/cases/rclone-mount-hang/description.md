# Case: rclone mount hang under concurrent git access

## Situation

A team mounts an S3 bucket as a filesystem workspace using rclone mount. Under 30 concurrent
developers doing git operations, the FUSE mount hangs. dmesg shows "connection aborted" and
"request timed out" messages. git status takes 45s single-user and hangs under concurrent load.

## Root Cause

1. `--vfs-cache-mode off` disables ALL caching — every stat/open/readdir call goes directly to S3.
2. git status generates ~10,000 stat() calls on a moderate repository.
3. At 50ms S3 RTT per stat: 10,000 × 50ms = 500 seconds minimum.
4. Under 30 concurrent users, stat calls accumulate → FUSE connection pool exhaustion → hang.

## Expected Diagnosis

- Category: mount_filesystem_workspace
- Subcategory: metadata_storm + cache_configuration
- Root cause: metadata amplification from uncached stat calls under concurrent load
- Confidence: high
