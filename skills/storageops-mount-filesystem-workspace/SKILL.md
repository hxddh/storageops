---
name: storageops-mount-filesystem-workspace
description: >
  Diagnose issues with object storage mounted as a filesystem (rclone mount,
  s3fs, goofys, JuiceFS). Covers POSIX semantic mismatches (no atomic rename,
  no symlinks, no locks), metadata amplification from stat/list-heavy workloads,
  cache consistency, and workspace/IDE performance on mounted storage. Use when
  user reports slow `ls`, `git` failures, file corruption, or high latency on
  mounted object storage.
maturity: stable
mode: light_heavy
estimated_tokens: 1300
trigger_keywords:
  - rclone mount
  - s3fs
  - goofys
  - JuiceFS
  - fuse
  - mounted storage
  - mount performance
  - mount corruption
  - git on s3
  - IDE slow
  - workspace on object storage
  - stat latency
  - filesystem emulation
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# Mount & Filesystem Workspace Diagnosis

Object storage is NOT a POSIX filesystem. Almost every mount issue stems from a semantic mismatch: tools (git, compilers, IDEs) expect POSIX behaviors that object storage doesn't provide natively.

## Decision Tree

```
Mount issue →
  ├─ "ls takes forever on a directory" → Metadata amplification (Step 3)
  ├─ "git status takes forever" → Stat amplification (Step 3 + Step 4)
  ├─ "file corruption on write" → Atomic rename missing (Step 4)
  ├─ "compiler/IDE won't work" → Lock/mmap/fcntl unsupported (Step 4)
  ├─ "stale data" → Cache coherence issue (Step 4)
  ├─ rclone mount specifically? → See rclone tuning (references/fuse.md)
  ├─ s3fs specifically? → See s3fs tuning (references/s3fs-tuning.md)
  └─ Unknown mount tool? → Ask: which mount tool, what filesystem operations fail
```

## Workflow

### Step 1: Identify Mount Type
rclone mount (VFS-based), s3fs (FUSE), goofys (FUSE, read-optimized), JuiceFS (metadata engine + object storage). Each has different capabilities.

### Step 2: Classify the I/O Pattern
- **Read-heavy**: IDE file watchers, git status, compilers reading headers
- **Write-heavy**: build artifacts, database files, log files
- **Stat-heavy**: `ls -la`, file managers, rsync dry-run
- **Metadata-heavy**: git operations, package managers (npm, pip), find

### Step 3: Measure Metadata Amplification
A single `ls` on a directory with 1000 files = 1000 HEAD/GET requests to object storage API. Git status = stat() on every file in the repo. This is the #1 performance killer. See `references/metadata-amplification.md`.

### Step 4: Check POSIX Semantic Mismatches
| Operation | POSIX Expectation | Object Storage Reality | Impact |
|-----------|------------------|----------------------|--------|
| Atomic rename | `rename(a,b)` is atomic | Not atomic (copy+delete) | File corruption during writes |
| Symlinks | Native kernel support | Emulated via metadata | `npm install` failures |
| File locks | `flock()` / `fcntl()` | Not supported | Database corruption, build failures |
| mmap | Kernel page cache | Not supported | ML model loading failures |
| Directory listing | `getdents()` is fast | N×HEAD/GET requests | Slow `ls`, git, IDE |

### Step 5: Tune the Mount
- **rclone mount**: `--vfs-cache-mode writes --vfs-cache-max-age 1h --dir-cache-time 5m`
- **s3fs**: `-o stat_cache_expire=300 -o enable_noobj_cache -o use_cache=/tmp/s3fs`
- **General**: Set `--attr-timeout` and `--dir-cache-time` high enough to reduce stat calls

## Output Format

```markdown
# Diagnosis: [one-line]
**Mount type**: [tool + version]
**Root cause**: metadata-amplification | posix-mismatch | cache-coherence | tool-bug
**Confidence**: high | medium | low

## Evidence
- Mount command: [sanitized]
- Failing operation: [e.g., git status, npm install]
- Latency observed: [operation → time]

## Analysis
- Stat amplification: [N files × HEAD/GET per operation]
- POSIX mismatch: [specific operation that's unsupported]

## Recommendations
1. **[mount option change]** — [expected effect]
2. **[workflow change]** — [e.g., use object storage SDK for writes, mount for reads]
3. **[alternative tool]** — [JuiceFS for POSIX-heavy workloads]
```

## Examples

### Example 1: git status takes 45 seconds
**Input**: rclone mount with a git repo of 5000 files. `git status` = 45s.
**Diagnosis**: Metadata amplification — git stat()s every file in the working tree. 5000 HEAD requests to S3 = ~45s at ~9ms RTT.
**Recommendation**: `--dir-cache-time 1h --attr-timeout 1h --vfs-cache-mode full`. Expect git status <3s after cache warm.

### Example 2: npm install failures
**Input**: npm install on mounted storage. Errors: `ENOTEMPTY`, `EEXIST`, `EPERM`.
**Diagnosis**: npm uses atomic rename for package installation. rclone mount rename is NOT atomic.
**Recommendation**: Use local filesystem for node_modules, mount for source code only. Or use `--vfs-cache-mode full`.

### Example 3: Build corruption on parallel make
**Input**: make -j8 on mounted directory. Random corruption in output binaries.
**Diagnosis**: Parallel writes to same file. Object storage has no `O_EXCL` or file locking. Multiple processes overwriting simultaneously.
**Recommendation**: Build locally, sync output to mount. Or reduce to `make -j1`. For production: JuiceFS with full POSIX emulation.

## References
- `references/fuse.md` — Comprehensive FUSE mount tuning guide
- `references/posix-semantics.md` — POSIX vs object storage behavior matrix
- `references/metadata-amplification.md` — Quantifying and reducing stat/HEAD amplification
- `references/vfs-cache-guide.md` — rclone VFS cache modes explained
- `references/s3fs-tuning.md` — s3fs mount options by workload
