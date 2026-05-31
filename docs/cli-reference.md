# CLI Reference

```
storageops <command> [options]
```

All commands operate on offline artifacts only. No cloud connections, no credentials required
except for `storageops diagnose` (and the REPL), which need Pi Coding Agent and an API key.

---

## Interactive REPL — `storageops`

Start the interactive session with no arguments:

```bash
storageops
```

Describe your problem in plain language or paste log output. Press Enter to submit.

```
StorageOps  anthropic  ·  type / for commands  ·  Ctrl+C to interrupt  ·  /exit to quit
  Session  a3f2b1c8

> Got 403 from boto3, here's the trace: ...
```

**Reference a local file:**
```
> analyze this log @/var/log/s3-error.log
```

**Slash commands** (type `/` to see the full list):

| Command | Action |
|---------|--------|
| `/help` | Show available commands |
| `/clear` | Start a fresh session |
| `/status` | Show session ID, Pi and API key status |
| `/doctor` | Check environment health |
| `/setup` | Re-run setup wizard |
| `/verbose` | Toggle verbose output (shows tool calls) |
| `/exit` | Quit |

**One-shot (pipe):**
```bash
storageops < error.log
aws s3 cp s3://bucket/key . 2>&1 | storageops
storageops @/path/to/s3-errors.log
```

---

## `storageops resume`

Resume a previous REPL session. Evidence and conversation turns are preserved.

```bash
storageops resume              # pick from recent sessions
storageops resume abc12345     # resume by session ID
```

Sessions are saved automatically to `~/.storageops/sessions/`. Use `resume` with no
arguments to see a numbered list of recent sessions; enter the number to load one.

---

## `storageops diagnose`

Run Pi Coding Agent for full multi-turn AI diagnosis. Requires Pi Coding Agent installed
and an API key configured (see `storageops setup`).

```bash
storageops diagnose <file|->  [options]
```

`agent` is a hidden alias for `diagnose` (identical behavior).

**What happens:**
1. Evidence file is read and secrets are redacted.
2. Domain is pre-classified (rule-based) and shown as pre-flight output.
3. BM25 memory is searched for similar past cases.
4. Pi is started in RPC mode with the redacted evidence file.
5. Pi loads StorageOps skills and calls diagnostic tools.
6. Pi returns a markdown report with YAML frontmatter.
7. StorageOps validates the report (safety, evidence sections, frontmatter).
8. Report is printed to stdout.

**Options:**
```
--stream                 Stream Pi output token-by-token to stdout
--runtime pi             Explicitly select Pi runtime (default)
--pi-command <path>      Path to pi binary (default: pi)
--pi-model <model>       Model hint passed to Pi
--pi-provider <provider> Provider hint passed to Pi
--max-turns N            Maximum Pi turns (default: 8)
--timeout-seconds N      Timeout in seconds (default: 600)
--format human|json      Output format (default: human)
--exit-code              Exit 1 if severity is high or critical (for CI)
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
## Key Evidence
...
## Remediation
- manual-only: `aws s3api ...`
```

**Examples:**
```bash
storageops diagnose error.log
storageops diagnose error.log --stream
storageops diagnose error.log --exit-code          # CI mode
storageops diagnose error.log --pi-model claude-opus-4-8
cat error.log | storageops diagnose -
```

---

## `storageops setup`

Guided setup wizard. Run once after install.

```bash
storageops setup
```

Walks through:
1. Downloading Pi Coding Agent binary (automatic).
2. Selecting your LLM provider (Anthropic / OpenAI).
3. Entering your API key (stored at `~/.storageops/config.json`).

---

## `storageops config`

Manage StorageOps configuration at `~/.storageops/config.json`.

```bash
storageops config list              # show all config (value of api_key is redacted)
storageops config get api_key       # get a specific key
storageops config set provider openai
storageops config set api_key sk-...
```

**Config keys:**

| Key | Default | Description |
|-----|---------|-------------|
| `provider` | (none) | LLM provider: `anthropic` or `openai` |
| `api_key` | (none) | API key for the provider |

---

## `storageops update`

Update Pi binary and reinstall skill files.

```bash
storageops update           # download latest Pi + reinstall skills
storageops update --check   # check for updates without installing
```

---

## `storageops doctor`

Check environment health: Python version, Pi binary, API key, skill files.

```bash
storageops doctor
```

---

## `storageops triage`

Classify evidence with rule-based pattern matching. No LLM, no Pi required. Instant.

```bash
storageops triage <file|->
```

**Options:**
```
--format human|json    Output format (default: human)
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

**Examples:**
```bash
storageops triage error.log
storageops triage error.log --format json
cat error.log | storageops triage -
```

---

## `storageops analyze`

Run the domain-specific parser and analyzer pipeline without an LLM. No Pi required.

```bash
storageops analyze <domain> <file|-> [options]
```

**Domains:**

| Domain | What it parses |
|--------|---------------|
| `s3_protocol_compatibility` | SigV4 XML errors, ETag mismatch |
| `cors_configuration` | CORS errors, NoSuchCORSConfiguration, preflight failures |
| `replication_versioning` | CRR/SRR ReplicationStatus, IAM/KMS failures |
| `bigdata_pipeline` | Hadoop/Spark S3A errors, committer failures |
| `cli_sdk_behavior` | rclone / s5cmd / AWS CLI debug logs |
| `performance_throughput` | Throttling (429/SlowDown), throughput data |
| `security_iam_policy` | 403 AccessDenied, IAM/bucket policy JSON |
| `lifecycle_cost` | Lifecycle XML, inventory data |
| `mount_filesystem_workspace` | FUSE mount, strace data |
| `network_endpoint_access` | dig/curl/ping/mtr connectivity output |

**Options:**
```
--format human|json    Output format (default: human)
--exit-code            Exit 1 if severity is high or critical (for CI)
```

**Examples:**
```bash
storageops analyze cli_sdk_behavior rclone.log
storageops analyze cors_configuration browser-console.log
storageops analyze security_iam_policy policy.json
storageops analyze performance_throughput s3-access.log
storageops analyze network_endpoint_access dig-output.txt
```

---

## `storageops scan`

Triage multiple files at once and print a summary table. (`batch` is a hidden alias.)

```bash
storageops scan <file> [<file> ...] [options]
```

**Options:**
```
--output <file>    Write a markdown summary report to this file
--format human|json
```

**Examples:**
```bash
storageops scan logs/*.log
storageops scan error1.log error2.log --output report.md
```

---

## `storageops report`

Generate a Markdown report from a saved analysis JSON file.

```bash
storageops report <analysis.json>
```

---

## `storageops memory`

Manage the persistent case memory at `~/.storageops/memory.jsonl`.
Memory is auto-populated after each successful `storageops diagnose` run.

```bash
storageops memory list   [--domain <domain>] [--limit 20]
storageops memory search <keywords...> [--domain <domain>]
storageops memory save   --domain <domain> --root-cause <type> --summary <text>
storageops memory export <output.jsonl> [--domain <domain>]
storageops memory import <input.jsonl>
```

**Examples:**
```bash
storageops memory list
storageops memory list --domain cli_sdk_behavior
storageops memory search "ETag mismatch multipart rclone"
storageops memory export backup.jsonl
```

---

## `storageops mcp`

Start the MCP (Model Context Protocol) stdio server.

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

Restart Claude Desktop after adding this config.

---

## `storageops serve`

Start the FastAPI HTTP API server and web UI.

```bash
storageops serve [--host 127.0.0.1] [--port 8080] [--reload]
```

**Requirements:** `pip install "storageops-cli[api]"` or `pip install fastapi uvicorn`

**Key endpoints:**

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web UI |
| `POST /triage` | `{"text": "..."}` → triage result |
| `POST /analyze` | `{"text": "...", "domain": "..."}` → analysis |
| `GET /health` | `{"status": "ok", "version": "..."}` |

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `STORAGEOPS_EMIT_METRICS` | Write triage confidence to `storageops-eval-metrics.json` after pytest |
| `GITHUB_ACTIONS` | Auto-enables metric emission in CI |
| `RUN_REAL_PI_SMOKE` | Set to `1` to run real Pi smoke tests in CI (disabled by default) |

Pi provider configuration (API keys, model, base URL) is managed in Pi Coding Agent —
not in StorageOps. Use `storageops config` or `storageops setup` for StorageOps-level config.
