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

---

## Install

```bash
pip install storageops
storageops setup
```

`setup` walks you through:
1. Installing [Pi Coding Agent](https://pi.ai/agent) (the AI backend) — automatically downloaded
2. Selecting your LLM provider (Anthropic / OpenAI) and entering your API key
3. Installing diagnostic skills to `~/.storageops/`

That's it. No config files to edit manually.

---

## Usage

### Interactive REPL (recommended)

```bash
storageops
```

Describe your problem in plain language, paste log output, or both.

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

**Slash commands:**

| Command | Action |
|---|---|
| `/help` | Show available commands |
| `/clear` | Start a fresh session |
| `/doctor` | Check environment health |
| `/setup` | Re-run setup wizard |
| `/verbose` | Toggle verbose output |
| `/exit` | Quit |

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

## Offline commands (no AI required)

These work without Pi Agent or an API key:

```bash
# Rule-based triage — instant, no LLM
storageops triage error.log

# Structured analysis for a specific domain
storageops analyze security_iam_policy error.log

# Render a saved analysis JSON as a report
storageops report analysis.json

# Health check
storageops doctor

# Run all golden-case regression tests
storageops eval --all
```

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
| `analyze_iam` | Deep IAM / permissions analysis |
| `analyze_network` | DNS, TLS, TCP, VPC endpoint diagnostics |
| `analyze_performance` | Throughput, throttling, prefix hotspot analysis |
| `analyze_cors` | CORS misconfiguration root cause |
| `analyze_lifecycle` | Lifecycle rule and cost analysis |
| `parse_rclone_log` | Parse rclone debug output → structured dict |
| `parse_aws_cli_debug` | Parse AWS CLI `--debug` trace → structured dict |
| `parse_s3_xml_error` | Parse S3 XML error response → structured dict |
| `parse_network_diagnostics` | Parse dig/curl -v/ping output → structured dict |
| `memory_search` | Search past diagnostic sessions |

**Tool input/output format:**

All tools accept `{"text": "<log content>"}` and return structured JSON:

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
severity: high
---

## Root Cause
...
```

**Programmatic use:**

```python
from storageops.runtime import PiRpcRuntime, AgentRunOptions

result = PiRpcRuntime(AgentRunOptions(stream=False)).run("error.log")
print(result.report_markdown)
print(result.ok)
```

---

## Requirements

- Python 3.10+
- Pi Coding Agent (auto-installed by `storageops setup`)
- One of: `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (configured during setup)

---

## Development

```bash
git clone https://github.com/hxddh/storageops
cd storageops
pip install -e storageops-cli/
make test        # run all tests
make lint        # ruff + mypy
make eval        # golden-case regression
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## Security

- All log content is treated as **untrusted input** — never executed as instructions
- Secrets (AK/SK, tokens, Authorization headers) are **automatically redacted** before the AI sees them
- StorageOps never connects to real cloud accounts or modifies cloud resources
- See [SECURITY.md](SECURITY.md) for the full security model
