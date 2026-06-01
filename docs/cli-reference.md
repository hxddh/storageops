# CLI Reference

## Interactive session — `storageops`

Run `storageops` to start an interactive session. That's the primary interface.

```bash
storageops                                         # start a session
storageops "getting 429 SlowDown on S3 uploads"   # start with a description
storageops @error.log                              # start with a file reference
storageops < error.log                             # pipe via stdin
aws s3 cp s3://bucket/key . 2>&1 | storageops      # pipe CLI output directly
```

Inside a session, type `/` to see all available commands:

| Command | Action |
|---------|--------|
| `/help` | Show available commands |
| `/resume` | Pick a past session to continue |
| `/clear` | Start a fresh session |
| `/status` | Show session ID, Pi and API key status |
| `/config` | View or change configuration (`/config set <key> <value>`) |
| `/memory` | Browse past diagnosed cases (`/memory search <query>`) |
| `/update` | Download latest Pi binary and reinstall skills |
| `/doctor` | Check environment health |
| `/setup` | Re-run setup (API key, Pi install) |
| `/verbose` | Toggle verbose output (shows tool calls) |
| `/exit` | Quit |

Sessions are saved automatically to `~/.storageops/sessions/`.

---

## First-time setup — `storageops setup`

Run once after installing:

```bash
storageops setup
```

Downloads Pi Coding Agent, asks for your API key, and saves configuration to `~/.storageops/config.json`. Provider is auto-detected from key prefix (`sk-ant-` → Anthropic, `sk-` → OpenAI).

---

## Server commands

### `storageops mcp`

Start the MCP (Model Context Protocol) stdio server for Claude Desktop and other MCP clients.

```bash
storageops mcp
```

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

### `storageops serve`

Start the FastAPI HTTP API server and web UI.

```bash
storageops serve [--host 127.0.0.1] [--port 8080] [--reload]
```

Requires: `pip install "storageops[api]"` (FastAPI + uvicorn).

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web UI |
| `POST /triage` | `{"text": "..."}` → triage result |
| `POST /analyze` | `{"text": "...", "domain": "..."}` → analysis |
| `GET /memory` | List recent cases |
| `GET /memory/search?q=…` | BM25 keyword search |
| `GET /health` | `{"status": "ok", "version": "..."}` |

---

## CI / scripting commands

These are hidden from `--help` but fully supported for automation pipelines.

### `storageops diagnose <file|->`

Run Pi Coding Agent for full AI diagnosis of a single evidence file.

```bash
storageops diagnose error.log
storageops diagnose error.log --stream
storageops diagnose error.log --exit-code    # exit 1 if severity high/critical
cat error.log | storageops diagnose -
```

`agent` is a hidden alias (identical behavior).

**Options:**
```
--stream                 Stream Pi output token-by-token
--max-turns N            Max Pi turns (default: 8)
--timeout-seconds N      Timeout in seconds (default: 600)
--format human|json      Output format (default: human)
--exit-code              Exit 1 if severity is high or critical
--verbose, -v            Print pre-flight details to stderr
```

**Output:** Markdown diagnostic report with YAML frontmatter:
```markdown
---
category: cli_sdk_behavior
root_cause_type: multipart_etag_format_mismatch
confidence: 0.92
severity: high
---
## Summary
...
## Remediation
- manual-only: aws s3api ...
```

### `storageops triage <file|->`

Rule-based domain classification. No LLM, no Pi required. Instant.

```bash
storageops triage error.log
storageops triage error.log --format json
cat error.log | storageops triage -
```

**JSON output:**
```json
{
  "ok": true,
  "primary_domain": "performance_throughput",
  "all_domains": ["performance_throughput", "cli_sdk_behavior"],
  "scores": {"performance_throughput": 0.55, "cli_sdk_behavior": 0.25},
  "evidence_quality": "partial",
  "recommended_next_command": "storageops analyze performance_throughput <file>"
}
```

### `storageops analyze <domain> <file|->`

Domain-specific parser + analyzer pipeline. No Pi required.

```bash
storageops analyze security_iam_policy policy.json
storageops analyze performance_throughput s3-access.log
storageops analyze cli_sdk_behavior rclone.log
storageops analyze network_endpoint_access dig-output.txt
```

**Domains:** `s3_protocol_compatibility`, `cors_configuration`, `replication_versioning`,
`bigdata_pipeline`, `cli_sdk_behavior`, `performance_throughput`, `security_iam_policy`,
`lifecycle_cost`, `mount_filesystem_workspace`, `network_endpoint_access`

### `storageops scan <files…>`

Triage multiple files at once and print a summary table.

```bash
storageops scan logs/*.log
storageops scan error1.log error2.log --output report.md
```

### `storageops report <analysis.json>`

Render a saved analysis JSON as Markdown.

```bash
storageops report analysis.json
```

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `STORAGEOPS_EMIT_METRICS` | Write triage confidence to `storageops-eval-metrics.json` after pytest |
| `GITHUB_ACTIONS` | Auto-enables metric emission in CI |
| `RUN_REAL_PI_SMOKE` | Set to `1` to run real Pi smoke tests in CI (disabled by default) |
