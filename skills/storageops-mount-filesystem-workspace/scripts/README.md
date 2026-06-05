# storageops-mount-filesystem-workspace Scripts

## `mount_workload_analyzer.py`

Offline suitability analyzer. Given a mount tool, a workload type, and optionally
a file count and RTT, it estimates metadata (HeadObject) amplification, lists the
POSIX features the workload needs that an object mount cannot provide (atomic
rename, locking, mmap), flags stale-cache risk, and gives a suitability verdict.

```bash
./mount_workload_analyzer.py --tool s3fs --workload git --files 5000 --rtt-ms 30 --json
```

Offline-only: no mounting, no network. Facts mirror `references/posix-semantics.md`
and `references/object-storage-as-filesystem.md`.

## Planned Scripts

### `fuse_stats_collector.sh`
Given a mount point and a test command, collect:
- syscall count by type (strace -c).
- Timing breakdown per syscall type.
- FUSE daemon CPU/memory usage.
- Mount connection pool utilization.

### `metadata_amplification_estimator.py`
For a given operation profile (stat calls, open calls, readdir calls), estimate:
- API requests generated per operation.
- Minimum latency based on RTT.
- Comparison to local SSD latency.

### `workspace_profiler.py`
Profile a workspace directory for object-storage-hostile patterns:
- Count of small files (< 64KB).
- Count of symlinks.
- Expected stat calls for `git status`.
- Expected writes for `npm install`.
- Risk score for each tool/pattern.

### `mount_config_auditor.sh`
Parse mount configuration (s3fs, rclone mount command) and:
- Check cache settings.
- Check concurrency limits.
- Check connection pool settings.
- Flag obviously suboptimal settings.
- Print recommendations.

## Principles

- All scripts analyze offline data (strace logs, mount configs, directory listings).
- No modification of production mounts.
- Strace must be used with caution in production (performance impact).
