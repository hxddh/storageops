# Workspace Layout and Object Storage

## What Lives in a Development Workspace?

A typical development/agent workspace contains:

### Source Code (Git Repository)
- `.git/` — Objects, refs, index, pack files.
- Source files, config files.
- **I/O pattern:** Heavy stat(), random reads (git operations), rename() for refs.

### Dependencies
- `node_modules/` — Thousands of small files.
- `venv/` / `.venv/` — Python packages, compiled extensions.
- `vendor/` — Go dependencies.
- **I/O pattern:** Many stat() calls for resolution, many small file reads.

### Build Artifacts
- `dist/`, `build/`, `target/` — Compiled outputs.
- **I/O pattern:** Sequential writes, reads for packaging.

### Caches
- `__pycache__/` — Python bytecode.
- `.cache/` — Tool-specific caches.
- **I/O pattern:** Frequent small reads/writes.

### Agent Workspace (OpenClaw, Amp, etc.)
- Configuration files (often YAML/JSON).
- Installed skills/packages.
- Session state, conversation logs.
- Temp files during execution.
- **I/O pattern:** Startup scan (many stats), periodic writes, many small files.

## Classification: Hot vs Cold vs Warm

| Type | Access Pattern | Object Storage Suitable? |
|---|---|---|
| **Hot** | Constant read/write, many stat calls, concurrent access | **NO** — Use local SSD |
| **Warm** | Periodic access, mostly reads, low concurrency | Yes (with cache) |
| **Cold** | Infrequent access, archival | Yes |

Development workspaces are **HOT** by nature and should not be stored directly on
object storage mounts.

## Recommended Architecture

### Tier 1: Local SSD (Hot)
- Git repositories.
- `node_modules`, `venv`, `vendor`.
- IDE/editor working files.
- Agent workspace (configuration, session state).
- Build artifacts during active development.

### Tier 2: Object Storage (Warm/Cold)
- Periodic backups of workspace state.
- Datasets, models, media files.
- Build cache archives.
- Completed session logs.
- Released artifacts.

### Sync Strategy
```
# Periodic snapshot from SSD to object storage
rclone sync /workspace remote:workspace-snapshots/$(date +%Y-%m-%d) --exclude node_modules/ --exclude .git/

# Restore from snapshot
rclone sync remote:workspace-snapshots/2024-06-15 /restored-workspace
```

## Workspace Startup Performance

A workspace startup that takes 1 minute on local SSD can take 3–10× longer on
object storage mount because:

1. Config file scanning: N × stat() → N × HeadObject.
2. Skill/package loading: reads of many small files.
3. Dependency resolution: target resolution through symlinks/chains.
4. Cache validation: stat() on cached files to check staleness.

Mount cache configuration can partially mitigate this.
