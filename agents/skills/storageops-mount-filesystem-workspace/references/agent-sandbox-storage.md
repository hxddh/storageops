# Agent Sandbox Storage

## Context

Coding agents (Codex, Claude Code, Amp, OpenClaw) use a workspace directory for:
- Project files (source code, configuration).
- Agent state (conversation history, progress files).
- Installed skills and extensions.
- Temporary outputs (build results, test results, analysis files).

The performance of this workspace directly affects agent responsiveness and user experience.

## Object Storage Mount as Agent Workspace: Risks

### 1. Startup Metadata Storm
When an agent starts:
- Scans workspace for config files (~tens to hundreds of stat calls).
- Loads installed skills/extensions (~tens of file reads).
- Initializes internal state (~writes to state files).

On object storage mount at 50ms RTT:
- 100 stat calls × 50ms = 5 seconds just for config scanning.
- File reads add more latency.
- Startup time multiplies by 3–5×.

### 2. Conversation Feedback Latency
During a conversation turn:
- Agent writes thought/plan to workspace files.
- Agent reads tool output files.
- Agent writes edited files.
- File watchers detect changes (if supported).

On object storage mount:
- Every read/write has RTT overhead.
- Small file writes may trigger full object PUT.
- Feedback time can increase from seconds to minutes.

### 3. Concurrent Access Instability
Under 30-concurrent conditions:
- Each agent session accesses the workspace from a different process.
- Mount connection pool is shared.
- FUSE daemon serializes some operations.
- Git operations from one session affect all sessions (metadata storm).
- Mount disconnections become probabilistic under load.

### 4. Package Manager Operations
Installing skills/packages:
- npm install writes thousands of small files.
- pip install writes to venv.
- Each write → full object PUT on write-through mounts.
- Package install times explode.

## Recommended Pattern

### Layered Storage Architecture

```
/workspace/local/        <-- Local SSD: hot agent workspace
    config/
    skills/
    state/
    projects/
    temp/

/workspace/artifacts/    <-- Object storage mount: artifacts
    datasets/
    models/
    releases/
    logs/
    snapshots/
```

### Startup Flow
1. Agent checks if local workspace exists and is fresh.
2. If not, sync from object storage snapshot (local → local copy).
3. Agent operates entirely on local SSD.
4. Periodically (or on session end), snapshot to object storage.

### Config Management
- Configuration files stored both locally and synced to object storage.
- Agent reads config from local SSD (fast).
- Config changes written to local SSD, synced to object storage for persistence.

## OpenClaw-Specific Considerations

OpenClaw workspace contains:
- `openclaw.yaml` — Configuration.
- `skills/` — Installed skills (small files).
- `sessions/` — Session state, conversation logs.
- `temp/` — Temporary files during execution.

The primary issue is the configuration and skill files being read at startup.
These are read-heavy (stat + read), not write-heavy. Cache configuration
(stat cache TTL, VFS cache) can substantially reduce startup latency for
read-heavy workloads.
