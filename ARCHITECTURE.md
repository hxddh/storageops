# StorageOps Architecture

## Overview

StorageOps is a two-layer system: a deterministic offline diagnostic engine (`storageops-core`)
and a CLI/runtime layer (`storageops-cli`) that bridges the engine with Pi Coding Agent.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User / CI / Claude Desktop                   │
└───────────┬──────────────────────────┬──────────────────────────────┘
            │ storageops triage/analyze │ storageops diagnose / MCP / serve
            ▼                          ▼
┌───────────────────────┐   ┌──────────────────────────────────────────┐
│   storageops-cli      │   │          Pi Coding Agent (external)      │
│                       │   │                                          │
│  cli.py               │   │  - Owns LLM provider, model registry     │
│  agent.py             │   │  - Owns ReAct loop, streaming            │
│  tool_registry.py     │◄──│  - Calls storageops tools via MCP/CLI    │
│  api_server.py (opt)  │   │  - Loads StorageOps skills               │
│  mcp_server.py (opt)  │   │                                          │
│  memory_store.py      │   └──────────────────────────────────────────┘
│  audit_logger.py      │
│  runtime/pi_rpc.py    │
└───────────┬───────────┘
            │  sys.path bridge (storageops/__init__.py)
            ▼
┌───────────────────────────────────────────────────────────────────┐
│                      storageops-core                               │
│                                                                   │
│  parsers/                   analyzers/           utils/           │
│  ├── parse_rclone_log       ├── analyze_cors      ├── signatures  │
│  ├── parse_sigv4_error      ├── analyze_cost      └── secret_scan │
│  ├── parse_awscli_debug     ├── analyze_policy                    │
│  ├── parse_lifecycle_xml    ├── analyze_replication               │
│  ├── parse_cors_error       ├── analyze_throughput                │
│  ├── parse_replication_*    ├── analyze_network                   │
│  ├── parse_hadoop_s3a       ├── analyze_metadata_amplification    │
│  ├── parse_network_diag     └── detect_throttling                 │
│  └── parse_s5cmd_*                                                │
└───────────────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────────┐
│                   agents/skills/                                   │
│                                                                   │
│  storageops-triage/            storageops-cors-configuration/     │
│  storageops-s3-protocol-*/     storageops-replication-*/          │
│  storageops-cli-sdk-*/         storageops-bigdata-pipeline/       │
│  storageops-performance-*/     storageops-security-iam-policy/    │
│  storageops-lifecycle-cost/    storageops-network-endpoint-*/     │
│  storageops-evidence-*/        storageops-eval-golden-cases/      │
└───────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### `storageops-core` — Deterministic Engine

**Must remain independent of Pi, LLM providers, and real cloud credentials.**

| Module type | Responsibility |
|-------------|---------------|
| `parsers/parse_*.py` | Transform raw text (logs, XML, JSON) into structured dicts |
| `analyzers/analyze_*.py` | Take parsed dicts, return diagnosis + recommendations |
| `utils/signatures.py` | Single source of truth for domain-pattern mapping (`auto_detect()`) |
| `utils/secret_scanner.py` | Scan and redact credentials from arbitrary text |

All modules use **flat imports** (e.g., `from parse_rclone_log import parse`). The CLI
adds the relevant `storageops-core` subdirectories to `sys.path` at import time.

### `storageops-cli` — CLI and Runtime Bridge

| Module | Responsibility |
|--------|---------------|
| `cli.py` | All CLI commands: triage, analyze, diagnose, batch, memory, audit, serve, mcp, eval |
| `agent.py` | Domain classification, evidence assessment, analysis routing, report generation |
| `tool_registry.py` | Declares tools (name + schema) for Pi/MCP; dispatches calls to core |
| `api_server.py` | FastAPI: REST endpoints + SSE streaming for the web UI |
| `mcp_server.py` | MCP stdio server wrapping the tool registry |
| `memory_store.py` | BM25 case memory (JSONL, zero deps): save/search/export/import |
| `audit_logger.py` | Append-only JSONL audit log of Pi sessions |
| `runtime/pi_rpc.py` | Start Pi in `--mode rpc`, send JSONL request, collect events, validate report |

### `agents/skills/` — Pi Skill Pack

StorageOps skill definitions that Pi loads. Each skill provides domain-specific diagnostic
workflows, evidence checklists, tool usage patterns, and safety constraints.

Skills instruct Pi on *how* to diagnose; `storageops-core` provides the *tools* Pi calls.

---

## Data Flow: `storageops diagnose`

```
evidence.log
    │
    ▼
secret_scanner.scan()          ← redact AK/SK, tokens, signed URLs
    │
    ▼
redacted-evidence.txt          ← temporary file, never logged
    │
    ▼
auto_detect(text)              ← rule-based domain classification (signatures.py)
    │
    ▼
memory.search()                ← BM25 prior case lookup (optional hint to Pi)
    │
    ▼
pi --mode rpc                  ← JSONL RPC: send request, stream events
    │  Pi calls tools via MCP / CLI:
    │  - scan_secrets(text)
    │  - parse_rclone_log(log_text)
    │  - analyze_policy(...)
    │  - search_memory(query)
    │  - ... (18 registered tools)
    │
    ▼
final_report event             ← markdown with YAML frontmatter
    │
    ▼
validate_agent_report()        ← check frontmatter, evidence section, safety
    │
    ▼
memory.save_case()             ← auto-save on success
audit_logger.log_session_end() ← record outcome
    │
    ▼
stdout                         ← clean markdown report
```

---

## Data Flow: `storageops triage` / `storageops analyze`

These commands bypass Pi entirely — pure offline, instant:

```
evidence.log → auto_detect() → domain + confidence → human/JSON output
evidence.log → parse_*()     → structured dict
             → analyze_*()   → diagnosis + recommendations → human/JSON output
```

---

## Module Dependency Rules

```
storageops-core  ──has no deps──►  (zero imports from storageops-cli or agents/)
storageops-cli   ──imports──►  storageops-core (via sys.path bridge)
agents/skills    ──calls──►  storageops-cli tools (via Pi tool dispatch)
```

**storageops-core must never import from storageops-cli.** This ensures core parsers and
analyzers can be used standalone, called from Pi directly, or tested without the CLI.

---

## Storage Layout

| Path | Content |
|------|---------|
| `~/.storageops/memory.jsonl` | BM25 case memory (auto-populated on each Pi success) |
| `~/.storageops/audit.jsonl` | Pi session audit log (append-only) |
| `/tmp/storageops-pi-*/redacted-evidence.txt` | Temporary redacted evidence file (deleted after session) |

---

## Key Design Decisions

**Flat module imports in storageops-core**: parsers and analyzers use `from parse_rclone_log import parse`
rather than `from storageops_core.parsers.parse_rclone_log import parse`. This allows Pi to
call individual parser scripts directly via its tool interface without needing to install the
package. The CLI bridges this with a `sys.path` injection in `storageops/__init__.py`.

**Pi owns the agent loop**: StorageOps does not implement a ReAct loop, model registry, or
token streaming. Pi Coding Agent handles all of that. StorageOps sends Pi a redacted evidence
file path and receives a validated diagnostic report.

**Zero core dependencies**: `storageops-core` has no runtime pip dependencies. This minimizes
attack surface, makes it auditable, and ensures it runs anywhere Python ≥ 3.9 is available.

**Report validation as a safety gate**: Every Pi-generated report passes through
`validate_agent_report()` before being shown to the user. This catches unsafe recommendations,
missing evidence sections, and any secrets that slipped through redaction.
