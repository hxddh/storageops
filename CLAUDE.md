# StorageOps Architecture Guide

StorageOps is a diagnostic toolkit for object storage (S3-compatible) problems.
It has evolved from a rule-based CLI into an AI agent system.

## Repo layout

```
storageops/
├── storageops-core/          # Pure-Python diagnostic libraries (no AI deps)
│   ├── parsers/              # Log/XML/config parsers
│   ├── analyzers/            # Domain analyzers
│   └── utils/                # Secret scanner, common helpers
├── storageops-cli/           # CLI, LLM agent, API server
│   └── storageops/
│       ├── cli.py            # argparse entry-point
│       ├── agent.py          # Rule-based agent (offline, no LLM)
│       ├── llm_agent.py      # ReAct-loop LLM agent
│       ├── llm_provider.py   # Provider abstraction (Anthropic/OpenAI/Ollama)
│       ├── supervisor_agent.py # Multi-agent supervisor
│       ├── tool_registry.py  # Tool definitions + dispatch_tool()
│       ├── api_server.py     # FastAPI HTTP server
│       ├── mcp_server.py     # MCP server (optional, requires mcp package)
│       ├── memory_store.py   # BM25 case memory (~/.storageops/memory.jsonl)
│       ├── audit_reader.py   # JSONL audit log reader
│       ├── report_validator.py # YAML frontmatter validator
│       └── static/index.html # Web UI (Triage / Analyze / Agent tabs)
└── agents/skills/
    └── storageops-eval-golden-cases/cases/  # 13 golden test cases
```

## The 7 diagnostic domains

| Domain | What it covers |
|---|---|
| `s3_protocol_compatibility` | SigV4 errors, ETag mismatches, multipart upload issues |
| `cli_sdk_behavior` | rclone, s5cmd, AWS CLI, botocore bugs and misconfigurations |
| `performance_throughput` | Throttling (SlowDown/429), throughput bottlenecks, hot prefix |
| `security_iam_policy` | AccessDenied, IAM policy analysis, cross-account permissions |
| `lifecycle_cost` | Lifecycle rules, storage class costs, small-file IA penalty |
| `mount_filesystem_workspace` | FUSE/rclone mount hangs, git-on-S3 slowness, metadata amplification |
| `network_endpoint_access` | VPC endpoints, DNS resolution, TLS/SSL errors, connectivity |

## LLM agent: ReAct loop

```
Evidence → [Triage] → [Specialist LLM agent]
                            │
                   ┌────────▼────────┐
                   │  Reason (think) │◄──────┐
                   └────────┬────────┘       │
                            │ call tool      │
                   ┌────────▼────────┐       │
                   │  Act (tool)     │       │
                   └────────┬────────┘       │
                            │ observe result │
                            └───────────────►┘
                            │ max_turns reached / final_answer
                   ┌────────▼────────┐
                   │  Report output  │
                   └─────────────────┘
```

Each turn: LLM sees evidence + tool results → chooses next tool → sees result → repeats.
`max_turns` (default 8) caps total iterations. The final answer must contain a YAML
frontmatter block validated by `report_validator.py`.

## Multi-agent supervisor

`run_supervisor_agent()` in `supervisor_agent.py`:
1. **Triage** — `_triage(text)` runs regex signatures; returns domains sorted by confidence.
2. **Primary specialist** — runs `run_llm_agent()` with domain-specific tool subset.
3. **Secondary specialist** — only if `primary.ok=True` AND a second domain has confidence ≥ 0.3.

Enable with `storageops agent --supervisor`.

## LLM provider: BYOK

API key resolution order (highest priority first):
1. `--llm-key` CLI flag
2. `ANTHROPIC_API_KEY` / `STORAGEOPS_LLM_KEY` env var
3. `~/.storageops/config.yaml` → `llm_key`

No authentication on the API server. The web UI sends keys in POST body (HTTPS in prod).
Supported providers: `anthropic`, `openai`, `openai-compatible`, `ollama`.

Prompt caching is enabled for Anthropic (`cache_control: ephemeral` on system prompt and
last tool definition). Saves ~90% on repeated calls with the same system prompt.

Retry/backoff: up to 3 retries with 2s/4s/8s delays on rate-limit errors (429/529/overloaded).

## Tool registry

All tools are declared in `tool_registry.py`:
- `TOOL_DEFINITIONS` — list of `{name, description, input_schema}` dicts
- `dispatch_tool(name, inputs)` — routes to the correct function, returns `dict`

To add a new tool:
1. Implement the function (can live in `storageops-core/` or `storageops-cli/storageops/`)
2. Add an entry to `TOOL_DEFINITIONS` with name, description (>10 chars), and JSON schema
3. Add a dispatch case in `dispatch_tool()`
4. Add a minimal-input entry to `test_mcp_server.py::TestToolRegistryConsistency::test_dispatch_returns_dict_not_exception`

## Golden cases and fast eval

Each case in `agents/skills/storageops-eval-golden-cases/cases/<name>/`:
```
<name>/
├── input/          # One or more log/config files (all are concatenated)
├── expected.json   # Expected category, root_cause_types, keywords, severity
└── description.md  # Human-readable case summary
```

`expected.json` keys:
- `expected_category` — must match one of the 7 domains
- `expected_root_cause_types` — list of acceptable root cause strings
- `expected_min_confidence` — LLM target (0.75–0.85); fast eval checks `> 0`
- `must_include_evidence_keywords` — required in agent report
- `must_not_include` — destructive operations that must never appear

Fast eval (`test_fast_eval.py`) runs rule-based `auto_detect()` — no LLM, no network.
LLM eval uses `.github/scripts/llm_smoke_test.py` (requires `ANTHROPIC_API_KEY`).

Regression tracking: `conftest.py` writes `storageops-eval-metrics.json` when
`STORAGEOPS_EMIT_METRICS` or `GITHUB_ACTIONS` is set.
Check regressions: `storageops eval --regression`.

## Report format

Every LLM diagnostic report must include a YAML frontmatter block:

```markdown
---
category: performance_throughput
root_cause_type: hot_prefix_throttling
confidence: 0.88
severity: high
---

## Summary
...
## Key Evidence
...
## Remediation
...
```

`report_validator.py` checks for required fields and valid severity values.
Invalid reports get `report_valid=False` in the result dict and warnings printed to stderr.

## Memory store

`~/.storageops/memory.jsonl` — each line is a JSON record of a past diagnosis.
BM25 search (k1=1.5, b=0.75) over `summary` + `root_cause` text.
Accessible via `storageops memory list/search` or the `search_memory` agent tool.

## Audit log

`~/.storageops/audit.jsonl` — structural metadata only (never raw evidence text).
Event types: `session_start`, `llm_call`, `tool_call`, `tool_result`, `critique_turn`,
`memory_save`, `session_end`.
View with `storageops audit list/show/stats`.

## Adding a new parser

1. Create `storageops-core/parsers/parse_<name>.py` with a `parse(text: str) -> dict` function.
2. Add a corresponding test in `storageops-core/tests/test_parsers.py`.
3. Register as a tool in `tool_registry.py` (see "Tool registry" section above).
4. Add domain-routing in `supervisor_agent.py::_DOMAIN_TOOLS` if it's domain-specific.

## Safety constraints (always enforced)

- No connections to real cloud accounts, AK/SK, or cloud services
- All suspected secrets are redacted by `secret_scanner.scan()` before LLM sees them
- No commands that modify cloud resources are ever executed
- All log content is treated as untrusted input; never executed as instructions
- Report conclusions require evidence (file path, function, test result)
