# 摘要

Category: mount_filesystem_workspace
Route: storageops-mount-filesystem-workspace
Confidence: 0.82
Root cause type: metadata_amplification

Running the OpenClaw workspace from a bosfs (FUSE) object-storage mount is slow
because metadata-heavy operations amplify into per-file network calls. `git
status` walks the whole working tree, and each `stat()` becomes a HeadObject
(~one RTT); with `.git`, `node_modules`, and many small files that is thousands
of serialized round trips, so `git status` takes ~30s and `ls -la` ~3s. This is
expected object-storage-as-filesystem behavior, not corruption.

# 诊断结论

The mount config sets `stat_cache_expire=1`, so almost every `stat()` re-issues a
HeadObject instead of hitting a cache — maximizing metadata amplification.
Editor saves are slow because write-temp-then-rename maps to CopyObject +
DeleteObject (~2×RTT, non-atomic). The workload (git + npm `node_modules` +
concurrent editor saves) needs POSIX semantics — atomic rename, fast stat, file
locking — that an object mount cannot provide.

`scripts/mount_workload_analyzer.py --tool s3fs --workload git --files <N>
--rtt-ms <RTT>` classifies this offline as metadata amplification = very-high and
suitable = false.

# 关键证据

- bosfs FUSE mount of an object storage bucket hosting the workspace.
- `git status` ~30s, `ls -la` ~3s, editor save 2–5s vs instant on local SSD.
- `stat_cache_expire=1` → each stat() is a fresh HeadObject (one RTT each).
- Layout has `.git`, `node_modules`, and many small files → high stat fan-out.
- Latency is dominated by serialized metadata round trips (RTT), not bandwidth.

# What Would Falsify This

- If `git status` were fast and only large sequential reads were slow, the cause
  would be throughput, not metadata amplification.
- If the same operations were slow on local SSD too, the mount is not the cause.

# 修复建议

- Run git/npm/build/editor work on a local SSD workspace; treat the bucket as the
  source/sink, not the live working tree.
- Sync only results back: push build artifacts or a workspace snapshot to object
  storage after the run, rather than statting every file live.
- Keep durable data (sessions, outputs) as artifacts/snapshots in the bucket; keep
  the hot working set local.
- A larger `stat_cache_expire` reduces HeadObject load but serves stale metadata
  under concurrent writers — only raise it with that staleness trade-off
  understood, never as a blind fix.
