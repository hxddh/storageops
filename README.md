# StorageOps

**AI-powered diagnostics for S3-compatible object storage.**

Paste an error log. Get a structured root-cause analysis with remediation steps — in seconds.

```
$ storageops
StorageOps  anthropic  ·  type / for commands  ·  Ctrl+C to interrupt  ·  /exit to quit
  Session  a3f2b1c8

> s3://my-bucket/data/file.csv — AccessDenied, but my IAM role has s3:GetObject

  ⠹  Analyzing…  4s

  ────────────────────────────────────────────────────────
  missing resource qualifier  HIGH  91%
  ────────────────────────────────────────────────────────

  Root cause: Your policy grants s3:GetObject on arn:aws:s3:::my-bucket
  but not arn:aws:s3:::my-bucket/* (the objects themselves).

  Fix:
    "Resource": [
      "arn:aws:s3:::my-bucket",
      "arn:aws:s3:::my-bucket/*"    ← add this line
    ]

  8s  ·  session a3f2b1c8
```

---

## What StorageOps diagnoses

| Domain | Examples |
|---|---|
| IAM / permissions | AccessDenied, missing policy statements, SCP blocks |
| S3 protocol errors | SignatureDoesNotMatch, wrong endpoint, SDK quirks |
| Performance | Throttling, hot prefix, slow multipart upload |
| Network / endpoint | DNS failure, TLS errors, VPC PrivateLink issues |
| CORS | Blocked browser requests, missing allowed origins |
| Lifecycle / cost | Transition rules, storage class analysis |
| CLI / SDK | rclone, s5cmd, aws-cli, boto3 error traces |
| Mount / filesystem | s3fs, goofys, mountpoint-s3 problems |
| Replication | CRR/SRR failures, delete marker propagation |
| Big data | Spark S3A, Iceberg, Delta Lake commit failures |

---

## Install

```bash
# From source
pip install -e storageops-cli/

# Optional: enhanced REPL with ghost-text suggestions
pip install -e "storageops-cli/[repl]"

# Optional: syntax highlighting in /view
pip install pygments

storageops setup
```

`setup` downloads [Pi Coding Agent](https://pi.dev), asks for your API key, and configures Pi to load StorageOps skills and the StorageOps tool Extension automatically. That's it.

---

## Usage

Run `storageops` to start a session. Everything is available via `/` inside:

```bash
storageops
storageops "getting 429 SlowDown on S3 uploads"   # start with a description
storageops @error.log                              # start with a file reference
storageops < error.log                             # pipe via stdin
aws s3 cp s3://bucket/key . 2>&1 | storageops      # pipe CLI output directly
```

### Multi-turn conversation

Context accumulates across turns — add evidence progressively:

```
> access denied on GetObject
> here's my bucket policy: @policy.json
> and the IAM role: @role.json
```

### Slash commands

Type `/` inside the session to see the full list:

| Command | What it does |
|---|---|
| `/help` | Show the command list |
| `/history` | Show command history (`/history <N>` for last N) |
| `/resume` | Pick a past session to continue |
| `/clear` | Start a fresh session |
| `/status` | Show session ID, turn count, Pi and API key status |
| `/config` | View or change configuration (`/config set <key> <value>`) |
| `/editor` | Open `$EDITOR` (vim/nano) to write a long prompt or paste a large log |
| `/view` | Open last report in a pager (`less -R`) for full-screen browsing |
| `/memory` | Browse past diagnosed cases (`/memory search <query>`) |
| `/update` | Download latest Pi binary and reinstall skills |
| `/verbose` | Toggle verbose mode — shows each tool call and result |
| `/doctor` | Run environment health check |
| `/setup` | Re-run setup (API key, Pi install) |
| `/exit` | Quit (`Ctrl+C` also works) |

**Prompt-line tips:**
- `$ cmd` — run a shell command; output is added as session evidence
- `@file` — attach a file by path (`@/var/log/err.log`), glob (`@*.log`), or fuzzy prefix (`@s5cmd`)
- `↓` at end of line — continue input on the next line (multi-line prompts)
- `↑`/`↓` or `Ctrl+R` — browse readline history
- `Tab` — complete slash commands or `@` file paths
- `prompt_toolkit` (optional, `pip install storageops[repl]`) — ghost-text history auto-suggestions

Sessions are saved automatically to `~/.storageops/sessions/`.

---

## Capturing traffic with httpmon

[httpmon](https://github.com/hxddh/https-traffic-inspector) wraps any CLI command and
captures wire-level HTTP/HTTPS traffic — giving StorageOps the real error XML, auth headers,
and per-request timing that tool logs don't expose.

```bash
go install github.com/hxddh/https-traffic-inspector@latest
```

```bash
# Pipe directly into a session
httpmon --format json aws s3 cp s3://bucket/key . 2>&1 | storageops

# Save as HAR, then reference
httpmon --har capture.har rclone copy remote:bucket/ ./local/
storageops @capture.har
```

| Diagnostic need | What httpmon captures |
|---|---|
| Full 403 error XML + `x-amz-request-id` | IAM / policy diagnosis |
| Exact `Authorization` header format | SigV4 vs SigV2 vs presigned |
| Clock skew (`x-amz-date` vs `Date` header) | `RequestExpired` diagnosis |
| Per-request TTFB + total timing | Throttling and latency patterns |
| Complete CORS preflight headers | CORS misconfiguration diagnosis |
| TLS error details and redirect chain | Network / endpoint diagnosis |

---

## Web UI / HTTP API

```bash
storageops serve            # starts on http://localhost:8080
storageops serve --port 9000 --host 0.0.0.0
```

Requires: `pip install "storageops[api]"` (FastAPI + uvicorn).

| Endpoint | Description |
|---|---|
| `GET /` | Web UI |
| `POST /triage` | `{"text": "…"}` → domain classification |
| `POST /analyze` | `{"text": "…", "domain": "…"}` → offline analysis |
| `POST /stream/triage` | SSE stream of triage events |
| `POST /analyze/stream` | SSE stream of analysis events |
| `GET /domains` | List all supported diagnostic domains |
| `GET /memory` | List recent diagnosed cases |
| `GET /memory/search?q=…` | BM25 search past cases |
| `GET /health` | `{"ok":true}` |

---

## For AI agents

### Pi Coding Agent (built-in)

StorageOps registers all 21 tools in Pi via a TypeScript Extension auto-discovered from
`.pi/extensions/storageops.ts`. No extra setup needed — tools are available as soon as Pi
starts in the project directory.

### Claude Desktop (MCP)

```bash
storageops mcp     # start MCP stdio server
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

**21 registered tools** (available to both Pi Extension and MCP):

| Tool | Description |
|---|---|
| `scan_secrets` | Redact AK/SK, tokens, and Authorization headers |
| `parse_rclone_log` | Parse rclone `-vv` debug log → transfer records and errors |
| `parse_awscli_debug` | Parse AWS CLI `--debug` trace → request/response timeline |
| `parse_sigv4_error` | Parse `SignatureDoesNotMatch` XML → canonical request diff |
| `parse_s5cmd_log` | Parse s5cmd `--log debug` output → operation records |
| `parse_cors_error` | Parse CORS error responses and preflight failure headers |
| `parse_lifecycle_xml` | Parse S3 lifecycle configuration XML → rule list with warnings |
| `parse_replication_status` | Parse CRR/SRR replication status data |
| `parse_hadoop_s3a` | Parse Hadoop/Spark S3A filesystem error logs |
| `parse_network_diagnostics` | Parse `dig`/`curl -v`/`ping`/`mtr`/`traceroute` output |
| `parse_httpmon_log` | Parse httpmon NDJSON or HAR → S3 signals (errors, timing, auth type) |
| `analyze_policy` | Trace a 403 AccessDenied through IAM and bucket policies |
| `analyze_throughput` | Analyze throughput against theoretical limits; identify bottleneck layer |
| `analyze_cors` | Generate a CORS configuration fix for detected preflight issues |
| `analyze_network` | Root-cause DNS/TLS/TCP/VPC endpoint failures |
| `analyze_replication` | Diagnose CRR/SRR replication failures |
| `analyze_cost` | Analyze per-prefix inventory data for storage cost attribution |
| `detect_throttling` | Detect 429/SlowDown patterns and estimate throttle onset rate |
| `generate_policy_fix` | Generate corrected IAM or bucket policy statements |
| `generate_lifecycle_fix` | Generate corrected lifecycle XML from identified rule issues |
| `search_memory` | Search past diagnosed cases by BM25 keyword similarity |

**Report format** — Pi produces natural responses: casual for greetings, structured analysis for logs and diagnostics. All outputs are safety-linted for secrets and dangerous operations.

```markdown
---
category: security_iam_policy
root_cause_type: missing_resource_qualifier
confidence: 0.91
severity: high
---
## Summary
...
## Key Evidence
...
## Remediation
- manual-only: aws iam put-role-policy ...
```

---

## CI / scripting

These commands are hidden from `--help` but fully supported for automation:

| Command | Description |
|---|---|
| `storageops diagnose <file\|->` | Full Pi AI diagnosis of a single evidence file |
| `storageops triage <file\|->` | Instant rule-based domain classification (no Pi required) |
| `storageops analyze <domain> <file\|->` | Domain-specific parser + analyzer pipeline (no Pi required) |
| `storageops scan <files…>` | Triage multiple files, print a summary table |
| `storageops report <json>` | Render a saved analysis JSON as Markdown |

---

## Skills

StorageOps ships 15 Pi skill definitions that load automatically. Each skill covers one
diagnostic domain with evidence checklists, recommended tool calls, and Light/Heavy dual-mode
diagnosis workflows.

| Skill | Maturity | Domain |
|---|---|---|
| storageops-triage | core | Entry point — classifies evidence and routes to the right skill |
| storageops-security-iam-policy | core | 403 AccessDenied, IAM policy, bucket policy, KMS |
| storageops-performance-diagnosis | core | Throttling, throughput bottlenecks, prefix hotspot |
| storageops-s3-protocol-compatibility | core | SigV4, ETag mismatch, multipart upload, CORS |
| storageops-evidence-reporting | core | Structured report generation |
| storageops-cli-sdk-diagnosis | mature | rclone, s5cmd, awscli, boto3 behavior |
| storageops-network-endpoint-access | mature | DNS, TLS, VPC endpoint, PrivateLink |
| storageops-lifecycle-cost | mature | Lifecycle rules, storage class cost analysis |
| storageops-mount-filesystem-workspace | mature | s3fs, FUSE mounts, agent workspace |
| storageops-replication-versioning | beta | CRR/SRR, delete markers, Object Lock |
| storageops-bigdata-pipeline | beta | Spark S3A, Iceberg, Delta Lake commit failures |
| storageops-data-consistency | beta | Stale reads, replica drift |
| storageops-migration-sync | beta | Cross-provider data migration |
| storageops-event-notification | experimental | S3 → Lambda/SQS/SNS event triggers |
| storageops-eval-golden-cases | — | Regression evaluation golden cases |

---

## Supported providers

- **AWS S3**
- **Alibaba Cloud OSS**
- **Baidu Cloud BOS**
- **Tencent Cloud COS**
- **Volcengine TOS**
- **MinIO**, **Ceph**, **Wasabi**, and other S3-compatible endpoints

---

## Requirements

- Python 3.9+
- Pi Coding Agent (auto-installed by `storageops setup`)
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (configured during setup)
- Optional: [httpmon](https://github.com/hxddh/https-traffic-inspector) for wire-level traffic capture
- Optional: `pygments` for syntax-highlighted `/view` reports
- Optional: `prompt_toolkit>=3.0` for ghost-text history suggestions (`pip install "storageops[repl]"`)

---

## Development

```bash
git clone https://github.com/hxddh/storageops
cd storageops
pip install -e storageops-cli/
make test        # no network or LLM required
make lint        # ruff
make eval        # golden-case regression
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## Security

- All log content is treated as **untrusted input** — never executed as instructions
- Secrets (AK/SK, tokens, Authorization headers) are **automatically redacted** before Pi sees them
- `parse_httpmon_log` classifies Authorization header type (`sigv4`/`presigned`/`anonymous`) but never returns the raw value
- StorageOps never connects to real cloud accounts or modifies cloud resources
- See [SECURITY.md](SECURITY.md) for the full security model
