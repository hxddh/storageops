# StorageOps

**AI-powered diagnostics for S3-compatible object storage.**

Paste an error log. Get a structured root-cause analysis with remediation steps — in seconds.

```
$ storageops
StorageOps  S3 Diagnostic Agent
Describe your issue or paste error logs. Use @file.log to reference a file.

> s3://my-bucket/data/file.csv — AccessDenied, but my IAM role has s3:GetObject

  Domain:  security iam policy  (91%)
  ────────────────────────────────────────────────────────
  MISSING RESOURCE QUALIFIER  HIGH  91%
  ────────────────────────────────────────────────────────

  Root cause: Your policy grants s3:GetObject on arn:aws:s3:::my-bucket
  but not arn:aws:s3:::my-bucket/* (the objects themselves).

  Fix:
    "Resource": [
      "arn:aws:s3:::my-bucket",
      "arn:aws:s3:::my-bucket/*"    ← add this line
    ]
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
pip install storageops
storageops setup
```

`setup` does three things automatically:
1. Downloads [Pi Coding Agent](https://pi.ai/agent) (the AI backend)
2. Asks for your LLM provider (Anthropic / OpenAI) and API key
3. Configures Pi to auto-load StorageOps diagnostic skills

That's it. Skills load automatically when the agent starts — no manual configuration needed.

---

## Usage

### Interactive REPL (recommended)

```bash
storageops
```

Describe your problem in plain language, paste log output, or both. Empty line submits.

```
> Got 403 from boto3, here's the trace:
  botocore.exceptions.ClientError: An error occurred (AccessDenied)
  when calling the GetObject operation: Access Denied
```

**Reference a local file** with `@path`:

```
> analyze this log @/var/log/s3-error.log
```

**Multiple turns** — StorageOps accumulates evidence across turns before running analysis:

```
> access denied on GetObject
> here's my bucket policy: @policy.json
> and the IAM role: @role.json
```

**REPL commands:**

| Command | What it does |
|---|---|
| `/help` | Print this command list |
| `/clear` | Discard the current session and start fresh |
| `/verbose` | Toggle verbose mode — shows tool calls and pre-flight classification details |
| `/doctor` | Run environment health check (Pi binary, API key, skills) without leaving the REPL |
| `/setup` | Re-run the setup wizard — re-download Pi or update API key without restarting |
| `/exit` | Quit (Ctrl+C also works) |

### Resume a past session

```bash
storageops resume            # show a numbered list of recent sessions to pick from
storageops resume abc12345   # resume a specific session by its 8-character ID
```

Sessions are saved automatically to `~/.storageops/sessions/`. All evidence blocks and
conversation turns are preserved and reloaded exactly as they were.

### One-shot (pipe / script)

Any argument that is not a known subcommand is treated as an initial REPL message:

```bash
# Describe a problem in plain language
storageops "getting 429 SlowDown on S3 uploads"

# Pipe a log file via stdin
storageops < error.log
aws s3 cp s3://bucket/key . 2>&1 | storageops

# Pass a file reference as the initial message
storageops @/path/to/s3-errors.log
```

### One-file diagnosis (Pi agent)

For a direct file-in → report-out workflow without the REPL:

```bash
storageops diagnose error.log
storageops diagnose error.log --stream          # stream Pi output live
storageops diagnose error.log --exit-code       # exit 1 on high/critical severity (CI)
storageops diagnose error.log --pi-model claude-opus-4-8
cat error.log | storageops diagnose -
```

---

## Configuration

```bash
storageops config list                  # show all config (api_key value is redacted)
storageops config get api_key           # get a specific key
storageops config set provider openai   # set LLM provider
storageops config set api_key sk-...    # set API key
```

Config is stored at `~/.storageops/config.json`.

## Updates

```bash
storageops update          # download latest Pi binary and reinstall skills
storageops update --check  # check for updates without installing
```

---

## Offline commands (no AI required)

These run entirely offline without Pi or an API key:

```bash
# Rule-based triage — instant domain classification
storageops triage error.log
storageops triage error.log --format json

# Domain-specific parser + analyzer pipeline
storageops analyze security_iam_policy error.log
storageops analyze performance_throughput s3-access.log
storageops analyze cli_sdk_behavior rclone-debug.log

# Triage multiple files at once
storageops scan *.log --output report.md

# Render a saved analysis JSON as a Markdown report
storageops report analysis.json

# Environment health check
storageops doctor
```

---

## Capturing traffic with httpmon

[httpmon](https://github.com/hxddh/https-traffic-inspector) wraps any CLI command and
captures the actual HTTP/HTTPS traffic. This gives StorageOps **wire-level evidence** —
the real error XML, auth headers, response timing — that tool logs don't expose.

**Install httpmon:**
```bash
go install github.com/hxddh/https-traffic-inspector@latest
```

**Use with StorageOps:**

```bash
# Capture and pipe directly into the REPL
httpmon --format json aws s3 cp s3://bucket/key . 2>&1 | storageops

# Capture to HAR file, then pass as a file reference
httpmon --har capture.har rclone copy remote:bucket/ ./local/
storageops @capture.har

# Direct Pi diagnosis of captured traffic
storageops diagnose capture.har
```

**What httpmon reveals that tool logs hide:**

| Diagnostic need | What httpmon captures |
|---|---|
| Full 403 error XML + `x-amz-request-id` | IAM / policy diagnosis |
| Exact `Authorization` header format | SigV4 vs SigV2 vs presigned |
| Clock skew (`x-amz-date` vs `Date` header) | `RequestExpired` diagnosis |
| Per-request TTFB + total timing | Throttling and latency patterns |
| Complete CORS preflight headers | CORS misconfiguration diagnosis |
| TLS error details and redirect chain | Network / endpoint diagnosis |

---

## Supported providers

StorageOps diagnoses issues across all S3-compatible storage:

- **AWS S3**
- **Alibaba Cloud OSS**
- **Baidu Cloud BOS**
- **Tencent Cloud COS**
- **Volcengine TOS**
- **MinIO**, **Ceph**, **Wasabi**, and other S3-compatible endpoints

---

## For AI agents

StorageOps exposes all diagnostic capabilities as MCP tools and a JSON API.

**Start the MCP server:**

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

**Available tools (21 total):**

| Tool | Description |
|---|---|
| `scan_secrets` | Redact AK/SK, tokens, and Authorization headers before processing |
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
| `analyze_network` | Root-cause DNS/TLS/TCP/VPC endpoint failures from parsed diagnostics |
| `analyze_replication` | Diagnose CRR/SRR replication failures |
| `analyze_cost` | Analyze per-prefix inventory data for storage cost attribution |
| `detect_throttling` | Detect 429/SlowDown patterns and estimate throttle onset rate |
| `generate_policy_fix` | Generate corrected IAM or bucket policy statements |
| `generate_lifecycle_fix` | Generate corrected lifecycle XML from identified rule issues |
| `search_memory` | Search past diagnosed cases by BM25 keyword similarity |

**Tool input/output format:**

All tools accept a primary string field (`text`, `log_text`, or similar) and return structured JSON:

```json
{
  "domain": "security_iam_policy",
  "root_cause_type": "missing_resource_qualifier",
  "confidence": 0.91,
  "severity": "high",
  "findings": ["Policy grants s3:GetObject on bucket ARN only"],
  "recommendations": ["Add /* suffix to resource ARN"]
}
```

**Report format** — every diagnostic report includes a machine-readable YAML frontmatter block:

```markdown
---
category: security_iam_policy
root_cause_type: missing_resource_qualifier
confidence: 0.91
confidence_factors:
  - factor: evidence_specificity
    weight: 0.5
severity: high
evidence_quality: sufficient
evidence_quality_score: 0.85
next_actions:
  - type: invoke_skill
    target: storageops-security-iam-policy
    priority: 1
---
```

**Programmatic use:**

```python
from storageops.runtime import PiRpcRuntime, AgentRunOptions

# run() accepts a file path; returns AgentRunResult with .ok and .report_markdown
result = PiRpcRuntime(AgentRunOptions(stream=False)).run("error.log")
print(result.report_markdown)
print(result.ok)
```

**Agent workflow with httpmon:**

```python
import subprocess
from storageops.tool_registry import dispatch_tool

# Step 1: capture wire-level traffic
proc = subprocess.run(
    ["httpmon", "--format", "json", "aws", "s3", "ls", "s3://my-bucket"],
    capture_output=True, text=True
)

# Step 2: parse with StorageOps MCP tool
parsed = dispatch_tool("parse_httpmon_log", {"log_text": proc.stdout})

# Step 3: signals route to the right skill
for signal in parsed["signals"]:
    print(signal)  # e.g. "access_denied_detected → security_iam_policy"
```

---

## Skill system

StorageOps ships a skill pack (v2 contract) that Pi loads automatically. Each skill covers
one diagnostic domain with evidence checklists, recommended tool calls, and Light/Heavy
dual-mode diagnosis workflows.

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

---

## Requirements

- Python 3.10+
- Pi Coding Agent (auto-installed by `storageops setup`)
- One of: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (configured during setup)
- Optional: [httpmon](https://github.com/hxddh/https-traffic-inspector) for wire-level traffic capture

---

## Development

```bash
git clone https://github.com/hxddh/storageops
cd storageops
pip install -e storageops-cli/
make test        # run all tests (107 tests, no network/LLM required)
make lint        # ruff + mypy
make eval        # golden-case regression
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## Security

- All log content is treated as **untrusted input** — never executed as instructions
- Secrets (AK/SK, tokens, Authorization headers) are **automatically redacted** before the AI sees them
- httpmon output: Authorization header **values** are never exposed — only classified as `sigv4`/`presigned`/`anonymous`
- StorageOps never connects to real cloud accounts or modifies cloud resources
- See [SECURITY.md](SECURITY.md) for the full security model
