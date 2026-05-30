# Object Storage as a Filesystem: The Fundamental Mismatch

## The Two Models

### Object Storage Model
- Flat namespace (no hierarchy, directories are simulated).
- Immutable objects (update = replace).
- Eventual consistency (some providers).
- ACID only at the object level.
- Optimized for whole-object access.
- HTTP-based, RTT-sensitive.

### POSIX Filesystem Model
- Hierarchical namespace (directories, trees).
- Mutable files (in-place updates, append, truncate).
- Strong consistency (usually).
- ACID with locking and journaling.
- Optimized for block-level access (4KB blocks, page cache).
- Local bus, microsecond latency.

## Why Mounts Are Necessary (And Why They Break)

Object storage mounts exist because:
1. Applications expect filesystem interfaces.
2. Users want familiar `ls`, `cp`, `cat` commands.
3. Legacy tools cannot be rewritten to use S3 APIs.

But mounting creates a leaky abstraction:
- `ls` appears to work → users assume POSIX semantics.
- `cat` works for small files → users assume `vim` will work.
- `cp` works → users assume `rsync` will be fast.
- Git clone works → users assume all git operations work.

## The "Good Enough" Threshold

Object storage mounts work acceptably when:
1. **Read-heavy, write-light.** Read cache handles most reads.
2. **Whole-file access.** Sequential read of entire files, no seeking.
3. **Low concurrency.** Single user/single process.
4. **High metadata cache TTL.** Changes infrequent enough to cache.
5. **Tolerant of latency.** Application doesn't require millisecond response.

Object storage mounts FAIL when:
1. **Heavy writes, especially small writes.**
2. **Random access patterns (seeking within files).**
3. **High concurrency (many processes, many stat calls).**
4. **Tools that expect POSIX semantics (git, databases, package managers).**
5. **Real-time or low-latency requirements.**

## When to Use Object Storage Mounts

| Use Case | Suitable? |
|---|---|
| Read-only dataset access | **YES** (with cache) |
| Media file serving (read-only) | **YES** (with cache) |
| Log archival and analysis | **YES** |
| Backup target (rsync/rclone to mount) | **YES** |
| Hot development workspace | **NO** |
| Database storage | **NO** |
| Real-time application I/O | **NO** |
| Concurrent multi-user workspace | **NO** |
| Git repository primary storage | **NO** |

## Alternatives to Mounting

1. **CLI/SDK tools directly:** awscli, rclone, s5cmd for specific operations.
2. **Application-level S3 SDK:** boto3, Go SDK for application integration.
3. **Hybrid:** Local SSD for hot data, object storage for cold data, sync between them.
4. **EFS/FSx/NFS:** True POSIX network filesystems (where available).
