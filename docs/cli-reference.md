# CLI Reference

```
storageops <command> [options]
```

All commands operate on offline artifacts only. No cloud connections, no API keys needed
except for `storageops agent` which requires Pi Coding Agent.

---

## `storageops triage`

Classify evidence with rule-based pattern matching. No LLM, no Pi required. Instant.

```bash
storageops triage <file|-|->
```

Reads from stdin when `file` is `-`.

**Options:**
```
--format human|json    Output format (default: human)
```

**Human output** (default): domain chip, confidence %, evidence quality badge, missing
evidence checklist, and a recommended next-step hint.

**JSON output** (`--format json`):
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
storageops analyze replication_versioning replication-status.json
storageops analyze security_iam_policy policy.json
storageops analyze lifecycle_cost lifecycle.xml
storageops analyze performance_throughput s3-access.log
storageops analyze network_endpoint_access dig-output.txt
```

---

## `storageops diagnose` / `storageops agent`

Run Pi Coding Agent for full multi-turn offline diagnosis. Requires Pi Coding Agent installed
and configured separately.

```bash
storageops diagnose <file|->  [options]
storageops agent    <file|->  [options]   # alias
```

`diagnose` is the preferred alias. Both commands are identical.

**What happens:**
1. Evidence file is read and secrets are redacted.
2. Domain is pre-classified and shown as pre-flight output.
3. BM25 memory is searched for similar past cases.
4. Pi is started in RPC mode and given the redacted evidence file path.
5. Pi loads StorageOps skills and calls diagnostic tools.
6. Pi returns a markdown report with YAML frontmatter.
7. StorageOps validates the report (safety, evidence sections, frontmatter).
8. Report is printed to stdout.

**Options:**
```
--stream                 Stream Pi output token-by-token to stdout
--runtime pi             Explicitly select Pi runtime (default and only option)
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
# Basic usage
storageops diagnose error.log

# Stream output as Pi generates it
storageops diagnose error.log --stream

# CI mode: exit 1 on high/critical severity
storageops diagnose error.log --exit-code

# Pass a model hint to Pi
storageops diagnose error.log --pi-model claude-opus-4-8

# Read from stdin
cat error.log | storageops diagnose -
```

---

## `storageops batch`

Triage multiple files at once and print a summary table.

```bash
storageops batch <file> [<file> ...] [options]
```

**Options:**
```
--output <file>    Write a markdown summary report to this file
--format human|json
```

**Example:**
```bash
storageops batch logs/*.log
storageops batch error1.log error2.log --output report.md
```

---

## `storageops report`

Generate a Markdown report from a saved analysis JSON file.

```bash
storageops report <analysis.json>
```

---

## `storageops eval`

Run rule-based golden case evaluation (no LLM, no Pi required).

```bash
# Evaluate all golden cases
storageops eval --all

# Evaluate a single case
storageops eval --case rclone-corrupted-transfer

# Regression check (compare latest two metric snapshots)
storageops eval --regression [--threshold 0.10]
```

**Options:**
```
--cases-dir DIR       Golden cases directory (default: agents/skills/storageops-eval-golden-cases/cases)
--outputs-dir DIR     Output directory for generated reports
--metrics-file FILE   Path to storageops-eval-metrics.json
--threshold FLOAT     Confidence drop that counts as regression (default: 0.10)
```

Exits with code 1 if any case fails or regression is detected.

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
storageops memory import backup.jsonl
```

---

## `storageops audit`

Inspect the audit log at `~/.storageops/audit.jsonl`. Records every agent session.

```bash
storageops audit list  [--limit 20]
storageops audit show  <session-id>
storageops audit stats
```

**`list`** — one line per session: timestamp, domain, outcome, runtime.

**`show`** — full event timeline for one session.

**`stats`** — aggregate: total sessions, Pi success rate, total redactions, runtime breakdown.

---

## `storageops serve`

Start the FastAPI HTTP API server and web UI.

```bash
storageops serve [--host 127.0.0.1] [--port 8080] [--reload]
```

**Requirements:** `pip install "storageops-cli[api]"` or `pip install fastapi uvicorn`

**Endpoints:**
| Endpoint | Description |
|----------|-------------|
| `GET /` | Web UI (4-tab: Diagnose / Analyze / Memory / About) |
| `POST /triage` | `{"text": "..."}` → triage result |
| `POST /analyze` | `{"text": "...", "domain": "..."}` → analysis |
| `GET /stream/triage` | SSE: real-time triage progress |
| `POST /analyze/stream` | SSE: streaming analysis |
| `GET /domains` | List all supported diagnostic domains |
| `GET /memory` | List recent diagnoses |
| `GET /memory/search?q=...` | BM25 search past diagnoses |
| `GET /health` | `{"status": "ok", "version": "..."}` |

**Options:**
```
--host    Bind address (default: 127.0.0.1 — localhost only)
--port    Port (default: 8080)
--reload  Auto-reload on code changes (development only)
```

---

## `storageops mcp`

Start the MCP (Model Context Protocol) stdio server for Claude Desktop.

```bash
storageops mcp
```

**Requirements:** `pip install "storageops-cli[mcp]"` or `pip install "mcp>=1.0"`

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

Restart Claude Desktop after adding this config. StorageOps diagnostic tools become
available as callable tools in conversations.

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `STORAGEOPS_EMIT_METRICS` | Write triage confidence to `storageops-eval-metrics.json` after pytest |
| `GITHUB_ACTIONS` | Auto-enables metric emission in CI |
| `RUN_REAL_PI_SMOKE` | Set to `1` to run real Pi smoke tests in CI (disabled by default) |

Pi provider configuration (API keys, model, base URL) is managed in Pi Coding Agent,
not in StorageOps. See Pi's documentation for provider setup.
