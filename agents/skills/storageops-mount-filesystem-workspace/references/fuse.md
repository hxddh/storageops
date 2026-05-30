# FUSE Mounts for Object Storage

## What is FUSE?

Filesystem in Userspace (FUSE) allows non-privileged users to create filesystem
implementations without editing kernel code. Object storage mount tools typically
use FUSE to translate filesystem operations to HTTP API calls.

## FUSE Lifecycle

```
Application (git, npm, IDE)
  → VFS (Kernel)
    → FUSE kernel module
      → /dev/fuse
        → FUSE daemon (s3fs, rclone mount, etc.)
          → HTTP client
            → Object storage API
```

Each filesystem operation crosses:
1. User space → kernel (syscall).
2. Kernel → /dev/fuse.
3. /dev/fuse → FUSE daemon.
4. FUSE daemon → HTTP request → network → provider.

## Latency Budget (per operation)

| Stage | Typical Cost |
|---|---|
| syscall + VFS | < 1 µs (local FS) |
| FUSE round-trip | ~10–100 µs |
| FUSE daemon processing | ~1–10 µs |
| HTTP request construction | ~1 ms |
| Network RTT | ~1–100 ms |
| Provider processing | ~5–100 ms |
| Total minimum | ~10 ms (optimistic) |
| Total typical | ~50–200 ms |

Compare to local SSD:
- stat: ~1 µs
- open: ~1 µs
- read: ~10 µs per 4KB block

**A single stat on a FUSE mount is 10,000–100,000× slower than local SSD.**

## FUSE Performance Options

### Metadata Cache (stat cache)
Controls how long stat information is cached:
- `-o stat_cache_expire=<seconds>` (s3fs)
- `--attr-timeout <duration>` (rclone mount)
- Default: typically 1–5 seconds.
- Increase for read-heavy workloads; decrease if objects change frequently.

### Write Cache
Controls whether writes are buffered:
- Write-through: Every write → immediate PUT (safe but slow).
- Write-back: Writes accumulate in cache, flushed asynchronously.
- `-o use_cache=<path>` (s3fs)

### Read Cache
- `-o ensure_diskfree=<MB>` (s3fs)
- Local disk cache of recently read objects.
- Critical for workspace workloads (file re-reads in development).

### Kernel Cache
- FUSE `-o kernel_cache` — Use kernel page cache.
- FUSE `-o auto_cache` — Kernel cache with attribute timeout.

## Common Mount Options (s3fs)

```
s3fs <bucket> <mountpoint> \
  -o url=https://<endpoint> \
  -o passwd_file=<credential-file> \
  -o use_cache=/tmp/s3fs-cache \
  -o ensure_diskfree=1024 \
  -o stat_cache_expire=300 \
  -o enable_noobj_cache \
  -o del_cache \
  -o multireq_max=20 \
  -o parallel_count=5 \
  -o multipart_size=16 \
  -o dbglevel=info \
  -o curldbg
```

Key parameters:
- `multireq_max` — Max parallel requests for listing.
- `parallel_count` — Max parallel requests for upload/download.
- `stat_cache_expire` — Metadata cache TTL in seconds.
- `use_cache` — Local disk cache path.
- `del_cache` — Directory listing cache.

## Common Mount Options (rclone mount)

```
rclone mount <remote>:<bucket> <mountpoint> \
  --vfs-cache-mode writes \
  --vfs-cache-max-size 1G \
  --dir-cache-time 5m \
  --attr-timeout 5m \
  --vfs-read-chunk-size 16M \
  --vfs-read-chunk-size-limit 64M \
  --buffer-size 16M \
  --transfers 4 \
  --daemon
```

Key parameters:
- `--vfs-cache-mode` — off, minimal, writes, full.
- `--dir-cache-time` — Directory listing cache TTL.
- `--attr-timeout` — File attribute cache TTL.
- `--vfs-read-chunk-size` — Read-ahead chunk size.

## FUSE Debugging

```bash
# Enable FUSE debug output
s3fs ... -o dbglevel=dbg -f  # foreground with debug

# Kernel FUSE messages
dmesg -w | grep -i fuse

# Strace the FUSE daemon (extreme detail)
strace -p <fuse-daemon-pid> -f -e trace=read,write,open,stat
```

## FUSE Failures

### Mount Hang / Unresponsive
- FUSE daemon stuck waiting for HTTP response.
- Deadlock in FUSE kernel module.
- Process enters D state (uninterruptible sleep).
- Check: `ps aux | grep ' D'`

### Transport Endpoint Not Connected
- FUSE daemon crashed or terminated.
- Kernel cannot communicate with userspace daemon.
- Requires: `fusermount -u <mountpoint>` or `umount <mountpoint>`.

### Input/Output Error (EIO)
- FUSE daemon returned an error to kernel.
- Often caused by HTTP 5xx or network timeout.
