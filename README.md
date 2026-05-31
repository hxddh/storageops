# StorageOps

**AI-powered diagnostics for S3-compatible object storage.**

Paste an error log. Get a structured root-cause analysis with remediation steps — in seconds.

```
$ storageops
StorageOps  S3 Diagnostic Agent
Describe your issue or paste error logs.

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

**Reference a local file:**

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
| `/help` | Show available REPL commands |
| `/clear` | Discard current session and start fresh |
| `/verbose` | Toggle verbose output (show tool calls and pre-flight details) |
| `/doctor` | Run environment health check without leaving the REPL |
| `/exit` | Quit (also: Ctrl+C) |

### Resume a past session

```bash
storageops resume            # pick from list of recent sessions
storageops resume abc12345   # resume by session ID
```

Sessions are saved automatically to `~/.storageops/sessions/`. Evidence from all turns is preserved and reloaded.

### One-shot (pipe / script)

```bash
# Pipe a log file
storageops < error.log

# Reference a file directly
storageops @/path/to/s3-errors.log

# Pipe from a command
aws s3 cp s3://bucket/key . 2>&1 | storageops
```

---

## Configuration

```bash
storageops config list           # show all config
storageops config get api_key    # get a specific key (value redacted)
storageops config set provider openai
```

Config is stored at `~/.storageops/config.json`.

## Updates

```bash
storageops update          # update Pi binary and reinstall skills
storageops update --check  # check without installing
```

---

## Offline commands (no AI required)

These work without Pi Agent or an API key:

```bash
# Rule-based triage — instant, no LLM
storageops triage error.log

# Structured analysis for a specific domain
storageops analyze security_iam_policy error.log

# Triage multiple files at once
storageops scan *.log --output report.md

# Render a saved analysis JSON as a report
storageops report analysis.json

# Health check
storageops doctor
```

---

## Capturing traffic with httpmon

[httpmon](https://github.com/hxddh/https-traffic-inspector) wraps any CLI command and captures the actual HTTP/HTTPS traffic. This gives StorageOps **wire-level evidence** — the real error XML, auth headers, response timing — that tool logs don't expose.

**Install httpmon:**
```bash
go install github.com/hxddh/https-traffic-inspector@latest
```

**Use with StorageOps:**

```bash
# Capture and pipe directly to StorageOps
httpmon --format json aws s3 cp s3://bucket/key . 2>&1 | storageops

# Capture to HAR file, then diagnose
httpmon --har capture.har rclone copy remote:bucket/ ./local/
storageops @capture.har

# One-shot diagnosis of captured traffic
storageops diagnose capture.har
```

**What httpmon reveals that tool logs hide:**

| Diagnostic need | What httpmon captures |
|---|---|
| Full 403 error XML + `x-amz-request-id` | IAM / policy diagnosis |
| Exact `Authorization` header format | SigV4 vs SigV2 vs presigned |
| Clock skew (`x-amz-date` vs `Date`) | `RequestExpired` diagnosis |
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

**Available tools via MCP:**

| Tool | Description |
|---|---|
| `triage` | Classify an evidence file and rank diagnostic domains |
| `scan_secrets` | Redact AK/SK, tokens, auth headers before processing |
| `parse_httpmon_log` | Parse httpmon NDJSON/HAR → S3 signals (errors, timing, auth type) |
| `parse_rclone_log` | Parse rclone debug output → structured dict |
| `parse_aws_cli_debug` | Parse AWS CLI `--debug` trace → structured dict |
| `parse_sigv4_error` | Parse SigV4 error XML → clock skew, canonical request diff |
| `parse_s3_xml_error` | Parse S3 XML error response → structured dict |
| `parse_network_diagnostics` | Parse dig/curl -v/ping output → structured dict |
| `analyze_policy` | Deep IAM / bucket policy evaluation |
| `analyze_network` | DNS, TLS, TCP, VPC endpoint root cause |
| `analyze_throughput` | Throughput, throttling, prefix hotspot analysis |
| `analyze_cors` | CORS misconfiguration root cause |
| `detect_throttling` | Detect 429/SlowDown patterns in logs |
| `generate_policy_fix` | Generate corrected IAM/bucket policy snippet |
| `search_memory` | Search past diagnostic sessions (BM25) |

**Tool input/output format:**

All tools accept `{"text": "<log content>"}` (or format-specific keys) and return structured JSON:

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

**Report format** — every diagnostic report includes a machine-readable YAML header:

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

result = PiRpcRuntime(AgentRunOptions(stream=False)).run("error.log")
print(result.report_markdown)
print(result.ok)
```

**Agent workflow with httpmon:**

```python
import subprocess, json

# Step 1: capture traffic
proc = subprocess.run(
    ["httpmon", "--format", "json", "aws", "s3", "ls", "s3://my-bucket"],
    capture_output=True, text=True
)

# Step 2: feed to StorageOps MCP tool
from storageops.tool_registry import dispatch_tool
parsed = dispatch_tool("parse_httpmon_log", {"log_text": proc.stdout})

# Step 3: signals tell you which skill to invoke
for signal in parsed["signals"]:
    print(signal)  # e.g. "access_denied_detected → security_iam_policy"
```

---

## Skill system

StorageOps uses a skill pack (v2 contract) to guide the Pi agent:

| Skill | Maturity | Domain |
|---|---|---|
| storageops-triage | core | Entry point — classifies and routes |
| storageops-security-iam-policy | core | 403, IAM, bucket policy, KMS |
| storageops-performance-diagnosis | core | Throttling, throughput, prefix hotspot |
| storageops-s3-protocol-compatibility | core | SigV4, ETag, multipart, CORS |
| storageops-evidence-reporting | core | Structured report generation |
| storageops-cli-sdk-diagnosis | mature | rclone, s5cmd, awscli, boto3 |
| storageops-network-endpoint-access | mature | DNS, TLS, VPC endpoint |
| storageops-lifecycle-cost | mature | Lifecycle rules, storage class cost |
| storageops-mount-filesystem-workspace | mature | s3fs, FUSE, agent workspace |
| storageops-replication-versioning | beta | CRR/SRR, delete markers, Object Lock |
| storageops-bigdata-pipeline | beta | Spark S3A, Iceberg, Delta Lake |
| storageops-data-consistency | beta | Stale reads, replica drift |
| storageops-migration-sync | beta | Cross-provider migration |
| storageops-event-notification | experimental | S3→Lambda/SQS/SNS triggers |

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
