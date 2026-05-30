# CLI Reference

```
storageops <command> [options]
```

---

## `storageops triage`

Classify evidence with rule-based pattern matching. No LLM, no key required. Instant.

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
  "missing_required": ["HTTP status code distribution", "request rate metrics"],
  "missing_helpful": ["prefix breakdown", "time series of error rate"],
  "secrets_redacted": 0
}
```

---

## `storageops analyze`

Run the domain-specific parser + analyzer pipeline without an LLM.

```bash
storageops analyze <domain> <file> [--subdomain throttling] [--no-redact]
```

**Domains:**
- `s3_protocol_compatibility` — SigV4 XML errors, ETag mismatch
- `cli_sdk_behavior` — rclone/s5cmd/AWS CLI debug logs
- `performance_throughput` — throttling, throughput analysis
- `security_iam_policy` — 403 AccessDenied, policy JSON
- `lifecycle_cost` — lifecycle XML, inventory data
- `mount_filesystem_workspace` — FUSE mount, strace data
- `network_endpoint_access` — connectivity, TLS, DNS

**Examples:**
```bash
# Parse an rclone log
storageops analyze cli_sdk_behavior rclone.log

# Analyze a lifecycle XML for cost issues
storageops analyze lifecycle_cost lifecycle.xml

# Analyze a 403 from policy JSON
storageops analyze security_iam_policy policy.json
```

**Options:**
- `--no-redact` — skip secret redaction (warning printed; review output before sharing)
- `--subdomain throttling` — force throttling analysis within performance_throughput
- `--object-size <MB>` — object size for throughput analysis
- `--rtt <ms>` — RTT for throughput analysis
- `--bandwidth <Mbps>` — bandwidth for throughput analysis

---

## `storageops agent`

Run the LLM-powered multi-turn diagnostic agent.

```bash
storageops agent <file> --llm-provider <provider> [options]
```

**Required:**
- `<file>` — evidence file (log, error output, config, or plain description)
- `--llm-provider anthropic|openai|openai-compatible|ollama`

**LLM options:**
```
--llm-provider   anthropic | openai | openai-compatible | ollama
--llm-model      Model name (default: claude-opus-4-8 for anthropic, gpt-4o for openai)
--llm-key        API key (prefer ANTHROPIC_API_KEY / OPENAI_API_KEY env var)
--llm-base-url   Base URL for openai-compatible or ollama (e.g. http://localhost:11434)
```

**Agent behavior options:**
```
--max-turns N    Maximum agent turns (default: 8; increase to 12 for complex cases)
--verbose, -v   Print tool calls and turn-by-turn progress to stderr
--stream         Stream LLM text output to stdout as it is generated
--supervisor     Multi-agent mode: triage → route → primary + optional secondary specialist
--interactive    After initial diagnosis, enter a REPL for follow-up questions
```

**Output:** Markdown diagnostic report to stdout, including YAML frontmatter:
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
# Anthropic Claude (recommended)
storageops agent error.log --llm-provider anthropic --verbose

# OpenAI GPT-4o
storageops agent error.log --llm-provider openai --llm-model gpt-4o

# Local Ollama
storageops agent error.log \
  --llm-provider ollama \
  --llm-base-url http://localhost:11434 \
  --llm-model llama3.1

# Multi-agent supervisor (best for complex multi-domain issues)
storageops agent error.log --llm-provider anthropic --supervisor

# Interactive follow-up
storageops agent error.log --llm-provider anthropic --interactive
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
> (nginx/caddy) in front and restrict access. API keys sent to `/agent` are used for
> the LLM call and are not logged or stored.

---

## `storageops mcp`

Start the MCP (Model Context Protocol) stdio server. Used by Claude Desktop.

```bash
storageops mcp
```

**Requirements:** `pip install "mcp>=1.0"`

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
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

After adding this, StorageOps tools appear in Claude Desktop as callable tools during conversations about object storage issues.

---

## `storageops memory`

List or search past LLM-diagnosed cases stored in `~/.storageops/memory.jsonl`.

```bash
storageops memory list [--domain <domain>] [--limit 20] [--verbose]
storageops memory search <keywords...> [--domain <domain>] [--limit 5]
```

**Examples:**
```bash
# List recent diagnoses
storageops memory list --verbose

# Search for ETag-related past cases
storageops memory search "ETag mismatch multipart rclone"

# Filter by domain
storageops memory search "403 AccessDenied" --domain security_iam_policy
```

---

## `storageops audit`

Inspect the JSONL audit log at `~/.storageops/audit.jsonl`. Tracks every agent session:
LLM calls, tool calls, token usage, outcomes.

```bash
storageops audit list [--limit 20] [--verbose]
storageops audit show <session-id>
storageops audit stats
```

**`list` output:** One line per session with timestamp, domain, outcome, turns, token count.

**`show` output:** Full timeline — every LLM call, tool call, and tool result for the session.

**`stats` output:** Aggregate JSON — total sessions, total tokens, tool frequency map,
average turns, critique confirmation rate, outcomes breakdown.

---

## `storageops eval`

Run golden case evaluation or regression check.

```bash
# Regression check (compare latest two metric snapshots)
storageops eval --regression [--metrics-file FILE] [--threshold 0.10]

# Single golden case evaluation
storageops eval --case rclone-corrupted-transfer \
  --cases-dir agents/skills/storageops-eval-golden-cases/cases \
  --outputs-dir docs/examples

# All cases
storageops eval --all \
  --cases-dir agents/skills/storageops-eval-golden-cases/cases
```

**`--regression` options:**
```
--metrics-file FILE   Path to storageops-eval-metrics.json (default: project root)
--threshold FLOAT     Confidence drop threshold (default: 0.10)
```

Exit code 1 when any regression is found.

---

## `storageops report`

Generate a Markdown report from a saved analysis JSON file.

```bash
storageops report analysis.json
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for `--llm-provider anthropic` |
| `OPENAI_API_KEY` | OpenAI API key for `--llm-provider openai` |
| `STORAGEOPS_LLM_KEY` | Generic key (used for any provider) |
| `STORAGEOPS_EMIT_METRICS` | Write triage confidence to `storageops-eval-metrics.json` after pytest |
| `GITHUB_ACTIONS` | Auto-enables metric emission in CI |

---

## Config File

`~/.storageops/config.yaml` — optional, loaded on every command:

```yaml
llm_key: sk-ant-...       # API key (any provider)
```

Set permissions: `chmod 600 ~/.storageops/config.yaml`
