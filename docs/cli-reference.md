# CLI Reference

```
storageops <command> [options]
```

---

## `storageops triage`

Classify evidence with rule-based pattern matching. No LLM, no API key required. Instant.

```bash
storageops triage <file>
```

**Output** (JSON to stdout):
```json
{
  "ok": true,
  "primary_domain": "performance_throughput",
  "all_domains": ["performance_throughput", "cli_sdk_behavior"],
  "scores": {"performance_throughput": 0.55, "cli_sdk_behavior": 0.25},
  "evidence_quality": "partial",
  "secret_scan": {"findings_count": 0, "has_secrets": false},
  "recommended_next_command": "storageops analyze performance_throughput <file>"
}
```

---

## `storageops analyze`

Run the domain-specific parser and analyzer pipeline without an LLM. No API key required.

```bash
storageops analyze <domain> <file> [options]
```

**Domains:**
- `s3_protocol_compatibility` — SigV4 XML errors, ETag mismatch
- `cli_sdk_behavior` — rclone / s5cmd / AWS CLI debug logs
- `performance_throughput` — throttling, throughput analysis
- `security_iam_policy` — 403 AccessDenied, policy JSON
- `lifecycle_cost` — lifecycle XML, inventory data
- `mount_filesystem_workspace` — FUSE mount, strace data
- `network_endpoint_access` — connectivity, TLS, DNS

**Options:**
```
--subdomain <name>      Force a specific subdomain (e.g. throttling)
--no-redact             Skip secret redaction (warning printed; review output before sharing)
--object-size <MB>      Object size for throughput analysis
--rtt <ms>              RTT for throughput analysis
--bandwidth <Mbps>      Bandwidth for throughput analysis
```

**Examples:**
```bash
storageops analyze cli_sdk_behavior rclone.log
storageops analyze lifecycle_cost lifecycle.xml
storageops analyze security_iam_policy policy.json
storageops analyze performance_throughput s3-access.log --subdomain throttling
```

---

## `storageops agent`

Run the LLM-powered multi-turn diagnostic agent.

```bash
storageops agent <file> [options]
```

**Provider is auto-detected** from the environment variable you set. You do not need to pass
`--llm-provider` if exactly one provider env var is set. See the table below.

**LLM options:**

```
--llm-provider   Provider name. Auto-detected from env var if not set.
                 Choices: anthropic | openai | deepseek | moonshot | qwen |
                          zhipu | groq | ollama | openai-compatible

--llm-model      Model name override. Default per provider:
                   anthropic  → claude-opus-4-8
                   openai     → gpt-5.5
                   deepseek   → deepseek-v4-pro
                   moonshot   → kimi-k2.6
                   qwen       → qwen3-max
                   zhipu      → glm-5.1
                   groq       → meta-llama/llama-4-scout-17b-16e-instruct
                   ollama     → llama3.3

--llm-key        API key. Prefer the provider env var instead.
--llm-base-url   Base URL for Ollama or a custom endpoint.
                 Ollama default: http://localhost:11434
```

**Agent behavior options:**

```
--max-turns N    Maximum agent turns (default: 8; use 12 for complex cases)
--verbose, -v    Print tool calls and turn-by-turn progress to stderr
--stream         Stream LLM text output to stdout token by token
--supervisor     Multi-agent mode: triage → route → primary + optional secondary specialist
--interactive    After initial diagnosis, open a follow-up REPL
```

**Output:** Markdown diagnostic report to stdout, with a YAML frontmatter block:

```markdown
---
category: cli_sdk_behavior
root_cause_type: multipart_etag_format_mismatch
confidence: 0.92
severity: high
---
## Summary
...
## Key Evidence
...
## Remediation
...
```

**Examples:**

```bash
# Auto-detect provider from env var (recommended)
storageops agent error.log

# Explicitly specify provider
storageops agent error.log --llm-provider anthropic
storageops agent error.log --llm-provider openai --llm-model gpt-4o
storageops agent error.log --llm-provider deepseek
storageops agent error.log --llm-provider groq

# Local Ollama (no API key required)
storageops agent error.log \
  --llm-provider ollama \
  --llm-base-url http://localhost:11434 \
  --llm-model llama3.3

# Custom OpenAI-compatible endpoint
export STORAGEOPS_LLM_KEY=your-key
storageops agent error.log \
  --llm-provider openai-compatible \
  --llm-base-url https://your-endpoint/v1 \
  --llm-model your-model

# Multi-agent supervisor (best for complex multi-domain issues)
storageops agent error.log --supervisor

# Verbose output to see each tool call
storageops agent error.log --verbose

# Interactive follow-up after initial diagnosis
storageops agent error.log --interactive

# Increase turns for complex cases
storageops agent error.log --max-turns 12
```

---

## `storageops serve`

Start the FastAPI HTTP API server and web UI.

```bash
storageops serve [--host 127.0.0.1] [--port 8080] [--reload]
```

**Requirements:** `pip install fastapi uvicorn`

**Endpoints:**
- `GET /` — Web UI (Triage / Analyze / Agent tabs)
- `POST /triage` — `{"text": "..."}` → triage result
- `POST /analyze` — `{"text": "...", "domain": "..."}` → analysis result
- `POST /agent` — `{"text": "...", "provider": "anthropic", "api_key": "sk-..."}` → diagnosis
- `GET /memory` — list recent diagnoses
- `GET /memory/search?q=ETag+mismatch` — search past diagnoses
- `GET /health` — `{"status": "ok"}`

**Options:**
```
--host    Bind address (default: 127.0.0.1 — localhost only)
--port    Port (default: 8080)
--reload  Auto-reload on code changes (development only)
```

> **Security note:** No authentication is built in. In production, put a TLS reverse proxy
> (nginx/caddy) in front and restrict access. API keys sent to `/agent` are used only for
> the LLM call and are not logged or stored.

---

## `storageops mcp`

Start the MCP (Model Context Protocol) stdio server for use with Claude Desktop.

```bash
storageops mcp
```

**Requirements:** `pip install "mcp>=1.0"`

**Claude Desktop configuration** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "storageops": {
      "command": "storageops",
      "args": ["mcp"]
    }
  }
}
```

After adding this config and restarting Claude Desktop, StorageOps diagnostic tools become available as callable tools during conversations.

---

## `storageops memory`

List or search past LLM-diagnosed cases stored in `~/.storageops/memory.jsonl`.

```bash
storageops memory list   [--domain <domain>] [--limit 20] [--verbose]
storageops memory search <keywords...> [--domain <domain>] [--limit 5]
```

**Examples:**
```bash
storageops memory list --verbose
storageops memory search "ETag mismatch multipart rclone"
storageops memory search "403 AccessDenied" --domain security_iam_policy
```

---

## `storageops audit`

Inspect the JSONL audit log at `~/.storageops/audit.jsonl`. Tracks every agent session:
LLM calls, tool calls, token usage, and outcomes.

```bash
storageops audit list  [--limit 20] [--verbose]
storageops audit show  <session-id>
storageops audit stats
```

**`list`** — One line per session: timestamp, session ID, domain, outcome, turns, token count.

**`show`** — Full timeline for one session: every LLM call, tool call, and result.

**`stats`** — Aggregate JSON: total sessions, total tokens, tool frequency map, average turns,
critique confirmation rate, outcome breakdown.

---

## `storageops eval`

Run golden case evaluation or regression check.

```bash
# Regression check (compare latest two metric snapshots)
storageops eval --regression [--metrics-file FILE] [--threshold 0.10]

# Evaluate a single golden case
storageops eval --case rclone-corrupted-transfer \
  --cases-dir agents/skills/storageops-eval-golden-cases/cases \
  --outputs-dir docs/examples

# Evaluate all cases
storageops eval --all \
  --cases-dir agents/skills/storageops-eval-golden-cases/cases
```

**`--regression` options:**
```
--metrics-file FILE   Path to storageops-eval-metrics.json (default: project root)
--threshold FLOAT     Confidence drop threshold to flag as regression (default: 0.10)
```

Exits with code 1 when any regression is found.

---

## `storageops report`

Generate a Markdown report from a saved analysis JSON file.

```bash
storageops report <analysis.json>
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key — auto-selects `anthropic` provider |
| `OPENAI_API_KEY` | OpenAI API key — auto-selects `openai` provider |
| `DEEPSEEK_API_KEY` | DeepSeek API key — auto-selects `deepseek` provider |
| `MOONSHOT_API_KEY` | Moonshot / Kimi API key — auto-selects `moonshot` provider |
| `DASHSCOPE_API_KEY` | Qwen / DashScope API key — auto-selects `qwen` provider |
| `ZHIPU_API_KEY` | Zhipu AI API key — auto-selects `zhipu` provider |
| `GROQ_API_KEY` | Groq API key — auto-selects `groq` provider |
| `STORAGEOPS_LLM_KEY` | Generic key fallback for any provider |
| `STORAGEOPS_LLM_MODEL` | Override default model without passing `--llm-model` |
| `STORAGEOPS_EMIT_METRICS` | Write triage confidence to `storageops-eval-metrics.json` after pytest |
| `GITHUB_ACTIONS` | Auto-enables metric emission in CI |

Provider auto-detection checks the env vars in the order shown above. The first one found
determines the provider. If multiple keys are set, use `--llm-provider` to be explicit.

---

## Config File

`~/.storageops/config.yaml` — optional, loaded on every command:

```yaml
llm_key: sk-ant-...         # API key (any provider)
llm_provider: anthropic     # Provider name (same values as --llm-provider)
llm_model: claude-opus-4-8  # Model override (same as --llm-model)
llm_base_url: ""            # Base URL for ollama or openai-compatible endpoint
```

Set permissions to protect the key:
```bash
chmod 600 ~/.storageops/config.yaml
```

Command-line flags always take precedence over the config file.
