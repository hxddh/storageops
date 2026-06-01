# StorageOps Architecture

## Overview

StorageOps is a two-layer system: a deterministic offline diagnostic engine (`storageops-core`)
and a CLI/runtime layer (`storageops-cli`) that bridges the engine with Pi Coding Agent.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   User / CI / Claude Desktop / AI Agents                 │
└───────────┬───────────────────────────┬─────────────────────────────────┘
            │ storageops triage/analyze  │ storageops (REPL/diagnose)
            ▼                           ▼
┌───────────────────────────┐   ┌──────────────────────────────────────────┐
│   storageops-cli          │   │          Pi Coding Agent (external)      │
│                           │   │                                          │
│  cli.py                   │   │  - Owns LLM provider, model registry     │
│  repl.py                  │   │  - Owns ReAct loop, streaming            │
│  session.py               │◄──│  - Calls tools via .pi/extensions/       │
│  agent.py                 │   │    storageops.ts (Pi Extension)          │
│  tool_registry.py         │   │  - Loads StorageOps skills               │
│  api_server.py (opt)      │   │                                          │
│  mcp_server.py (opt)      │   └──────────────────────────────────────────┘
│  memory_store.py          │              │
│  audit_logger.py          │              │ tool call
│  config.py                │              ▼
│  runtime/pi_rpc.py        │   ┌──────────────────────────────────────────┐
│  runtime/tool_bridge.py   │◄──│  .pi/extensions/storageops.ts            │
└───────────┬───────────────┘   │  (TypeScript, auto-discovered by Pi)     │
            │                   │  pi.registerTool() × 21                  │
            │                   │  → spawnSync python3 tool_bridge.py      │
            │                   └──────────────────────────────────────────┘
            │  sys.path bridge (storageops/__init__.py)
            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      storageops-core                                   │
│                                                                       │
│  parsers/                    analyzers/           utils/              │
│  ├── parse_rclone_log        ├── analyze_cors      ├── signatures     │
│  ├── parse_sigv4_error       ├── analyze_cost      └── secret_scanner │
│  ├── parse_awscli_debug      ├── analyze_policy                       │
│  ├── parse_lifecycle_xml     ├── analyze_replication                  │
│  ├── parse_cors_error        ├── analyze_throughput                   │
│  ├── parse_replication_*     ├── analyze_network                      │
│  ├── parse_hadoop_s3a        ├── analyze_metadata_amplification       │
│  ├── parse_network_diag      └── detect_throttling                    │
│  ├── parse_httpmon_log                                                │
│  └── parse_s5cmd_*                                                    │
└───────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                   agents/skills/                                       │
│                                                                       │
│  storageops-triage/             storageops-security-iam-policy/       │
│  storageops-s3-protocol-*/      storageops-lifecycle-cost/            │
│  storageops-cli-sdk-*/          storageops-network-endpoint-*/        │
│  storageops-performance-*/      storageops-evidence-reporting/        │
│  storageops-mount-filesystem-*/ storageops-replication-versioning/   │
│  storageops-bigdata-pipeline/   storageops-data-consistency/          │
│  storageops-migration-sync/     storageops-event-notification/        │
│  storageops-eval-golden-cases/                                        │
└───────────────────────────────────────────────────────────────────────┘
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
| `cli.py` | All CLI commands: resume, diagnose, config, update, setup, doctor, triage, analyze, scan, report, memory, mcp, serve, eval |
| `repl.py` | Interactive session (Pi Coding Agent-style); single-Enter input, slash commands, session persistence |
| `session.py` | Session persistence: save/load/list sessions in `~/.storageops/sessions/` |
| `agent.py` | Domain classification, evidence assessment, analysis routing, report generation |
| `config.py` | Read/write `~/.storageops/config.json` (api_key, provider) |
| `tool_registry.py` | Declares tools (name + schema) for MCP and HTTP API; `dispatch_tool()` routes to core |
| `api_server.py` | FastAPI: REST endpoints + SSE streaming for the web UI |
| `mcp_server.py` | MCP stdio server for Claude Desktop and other MCP clients (independent of Pi) |
| `memory_store.py` | BM25 case memory (JSONL, zero deps): save/search/export/import |
| `audit_logger.py` | Append-only JSONL audit log of Pi sessions |
| `runtime/pi_rpc.py` | Start Pi in `--mode rpc`, send `prompt` command via JSONL, collect events until `agent_end`, validate report |
| `runtime/tool_bridge.py` | Subprocess entry point called by the Pi Extension; reads `{tool, inputs}` from stdin, calls `dispatch_tool()`, writes JSON result to stdout |
| `prompts/pi_diagnosis_prompt.md` | System prompt template sent to Pi with each diagnosis; defines evidence collection strategy, safety rules, and required report format (YAML frontmatter + section headings) |

### `agents/skills/` — Pi Skill Pack

StorageOps skill definitions (v2 contract) that Pi loads. Each skill provides domain-specific
diagnostic workflows, evidence checklists, recommended tool calls, and safety constraints.

Skills instruct Pi on *how* to diagnose; `.pi/extensions/storageops.ts` provides the *tools* Pi calls natively.

**Skills v2 contract** — every skill has:
- Frontmatter: `maturity`, `mode`, `estimated_tokens`, `trigger_keywords`, `recommended_tools`
- Recommended Tool Calls table
- Diagnosis workflow with Light/Heavy dual mode and Thinking framework
- Output Envelope v2: `confidence_factors`, `evidence_quality_score`, `next_actions`

---

## Data Flow: REPL / `storageops diagnose`

```
User input (or evidence file)
    │
    ▼
secret_scanner.scan()          ← redact AK/SK, tokens, signed URLs
    │
    ▼
redacted text / temp file      ← never logged
    │
    ▼
auto_detect(text)              ← rule-based domain classification (signatures.py)
    │
    ▼
memory.search()                ← BM25 prior case lookup (optional hint to Pi)
    │
    ▼
pi --mode rpc                  ← JSONL RPC stdin/stdout (bidirectional, stdin stays open)
    │  {"type":"prompt","message":"..."}
    │
    │  Pi calls tools natively via .pi/extensions/storageops.ts:
    │  - scan_secrets        parse_rclone_log     analyze_policy
    │  - parse_awscli_debug  parse_sigv4_error    analyze_cost
    │  - detect_throttling   analyze_throughput   search_memory
    │  - ... (21 tools total, each → python3 tool_bridge.py)
    │
    ▼
agent_end event                ← {messages: [{role:"assistant", content:[{type:"text",...}]}]}
    │
    ▼
validate_agent_report()        ← check frontmatter, evidence section, safety
    │
    ▼
session.save()                 ← auto-save session to ~/.storageops/sessions/
memory.save_case()             ← auto-save to memory on success
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

## Storage Layout

| Path | Content |
|------|---------|
| `~/.storageops/config.json` | API key, provider selection |
| `~/.storageops/sessions/` | REPL session files (auto-saved, one JSON per session) |
| `~/.storageops/memory.jsonl` | BM25 case memory (auto-populated on each Pi success) |
| `~/.storageops/audit.jsonl` | Pi session audit log (append-only) |
| `/tmp/storageops-pi-*/redacted-evidence.txt` | Temporary redacted evidence file (deleted after session) |

---

## Module Dependency Rules

```
storageops-core  ──has no deps──►  (zero imports from storageops-cli or agents/)
storageops-cli   ──imports──►  storageops-core (via sys.path bridge)
agents/skills    ──loaded by──►  Pi (workflow guidance only; tools registered separately)
.pi/extensions   ──calls──►  storageops-cli (via tool_bridge.py subprocess)
```

**storageops-core must never import from storageops-cli.** This ensures core parsers and
analyzers can be used standalone, called from Pi directly, or tested without the CLI.

---

## Key Design Decisions

**Flat module imports in storageops-core**: parsers and analyzers use `from parse_rclone_log import parse`
rather than `from storageops_core.parsers.parse_rclone_log import parse`. The CLI bridges this
with a `sys.path` injection in `storageops/__init__.py`; `tool_bridge.py` sets up the same paths
for standalone invocation from the Pi Extension.

**Pi Extension as the tool bridge**: Pi does not support MCP as a client ("No MCP" — pi.dev/docs).
Tools are registered via a TypeScript Pi Extension (`.pi/extensions/storageops.ts`) using
`pi.registerTool()`. Each tool call spawns `python3 tool_bridge.py` as a subprocess, which
calls `dispatch_tool()` and returns the JSON result. This is the only supported way to give
Pi access to StorageOps diagnostic functions.

**Pi owns the agent loop**: StorageOps does not implement a ReAct loop, model registry, or
token streaming. Pi Coding Agent handles all of that. StorageOps sends Pi a redacted evidence
file path and receives a validated diagnostic report.

**Zero core dependencies**: `storageops-core` has no runtime pip dependencies. This minimizes
attack surface, makes it auditable, and ensures it runs anywhere Python ≥ 3.10 is available.

**Session persistence**: the REPL auto-saves each session (evidence blocks + conversation turns)
to `~/.storageops/sessions/<id>.json`. Type `/resume` inside a session to load any past session without loss of context.

**Report validation as a safety gate**: every Pi-generated report passes through
`validate_agent_report()` before being shown to the user. This catches unsafe recommendations,
missing evidence sections, and any secrets that slipped through redaction.

**Auth values never exposed**: `parse_httpmon_log` classifies Authorization header values
(sigv4/presigned_url/sigv2_deprecated/anonymous/other) but never returns the raw value.
This applies to HAR and NDJSON httpmon output alike.
