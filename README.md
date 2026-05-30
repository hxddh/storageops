# StorageOps

[![CI](https://github.com/hxddh/storageops/actions/workflows/ci.yml/badge.svg)](https://github.com/hxddh/storageops/actions)

Autonomous diagnostic agent for S3-compatible object storage. Diagnoses access errors, throttling, lifecycle cost issues, FUSE mount hangs, TLS failures, and more — offline, no cloud connections required.

---

## Install

**Requirements:** Python 3.9 or later, pip

```bash
# Clone the repo
git clone https://github.com/hxddh/storageops.git
cd storageops

# Install with LLM support
pip install -e "storageops-cli/[llm]"

# Verify
storageops --help
```

---

## Configure

Set the API key for whichever LLM provider you use. The agent auto-detects it — no other configuration needed.

```bash
# Pick one:
export ANTHROPIC_API_KEY=sk-ant-...     # Anthropic Claude  (recommended)
export OPENAI_API_KEY=sk-...            # OpenAI GPT-4o
export DEEPSEEK_API_KEY=sk-...          # DeepSeek
export MOONSHOT_API_KEY=sk-...          # Moonshot / Kimi
export DASHSCOPE_API_KEY=sk-...         # Qwen / Alibaba Cloud
export ZHIPU_API_KEY=...                # Zhipu / GLM
export GROQ_API_KEY=gsk_...             # Groq
```

To make this permanent, add the `export` line to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.).

---

## Run

```bash
storageops agent /path/to/your/error.log
```

The agent reads your log, calls diagnostic tools, reasons through the evidence, and prints a structured report with the root cause and remediation steps.

**Example output:**

```
---
category: cli_sdk_behavior
root_cause_type: multipart_etag_format_mismatch
confidence: 0.92
severity: high
---

## Summary
rclone uses MD5-of-parts ETag format for multipart uploads, which doesn't
match the server's expected format, causing all transfers to be flagged as corrupted.

## Key Evidence
- ETag mismatch detected on all objects > 5 MB
- rclone v1.64.2, remote: AWS S3

## Remediation
# manual-only: add to rclone.conf under [s3-remote]:
s3_upload_cutoff = 200Mi
```

---

## Supported Providers

| Provider | Env var | Default model |
|---|---|---|
| Anthropic Claude | `ANTHROPIC_API_KEY` | claude-opus-4-8 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat |
| Moonshot / Kimi | `MOONSHOT_API_KEY` | moonshot-v1-8k |
| Qwen / Alibaba Cloud | `DASHSCOPE_API_KEY` | qwen-max |
| Zhipu / GLM | `ZHIPU_API_KEY` | glm-4-plus |
| Groq | `GROQ_API_KEY` | llama-3.3-70b-versatile |
| Ollama (local, no key) | — | llama3.2 |

**Ollama:**
```bash
ollama pull llama3.1
storageops agent error.log --llm-provider ollama --llm-model llama3.1
```

**Custom OpenAI-compatible endpoint:**
```bash
export STORAGEOPS_LLM_KEY=your-key
storageops agent error.log \
  --llm-provider openai-compatible \
  --llm-base-url https://your-endpoint/v1 \
  --llm-model your-model
```

---

## Diagnostic Domains

The agent automatically routes to the right specialist based on your evidence:

| Domain | Diagnoses |
|---|---|
| `s3_protocol_compatibility` | SigV4 errors, clock skew, ETag mismatch, multipart |
| `cli_sdk_behavior` | rclone, s5cmd, AWS CLI, botocore errors |
| `performance_throughput` | Throttling (SlowDown/429), hot prefix, slow transfers |
| `security_iam_policy` | 403 AccessDenied, IAM/bucket policy, KMS, cross-account |
| `lifecycle_cost` | Lifecycle rules, STANDARD_IA small-file penalty |
| `mount_filesystem_workspace` | FUSE mount hangs, git-on-S3 slowness |
| `network_endpoint_access` | VPC endpoints, DNS, TLS/SSL certificate errors |

---

## Agent Options

```
storageops agent <file> [options]

  --llm-provider    Override auto-detected provider
  --llm-model       Override default model
  --llm-key         API key (prefer env var)
  --llm-base-url    Base URL for ollama or custom endpoint
  --max-turns N     Max reasoning turns (default: 8; use 12 for complex cases)
  --verbose         Show each tool call and result
  --stream          Stream output token by token
  --supervisor      Multi-agent mode: triage → route → specialists
  --interactive     Follow-up REPL after the initial diagnosis
```

---

## Other Commands

```bash
# Instant rule-based triage — no API key needed
storageops triage error.log

# Web UI (Triage / Analyze / Agent tabs)
pip install fastapi uvicorn
storageops serve        # open http://localhost:8080

# MCP server for Claude Desktop
pip install "mcp>=1.0"
storageops mcp

# Search past diagnoses
storageops memory search "ETag mismatch"

# View session history and token usage
storageops audit list
storageops audit stats
```

---

## Safety

- Secrets (AK/SK, tokens, auth headers) are redacted before evidence reaches the LLM
- All remediation steps are labeled `# manual-only:` — the agent never touches cloud resources
- No cloud connections — works entirely on the files you provide

---

## Docs

- [Getting Started](docs/getting-started.md) — step-by-step walkthrough with examples
- [CLI Reference](docs/cli-reference.md) — all commands and flags
- [Architecture](CLAUDE.md) — internals: ReAct loop, tool registry, skill loading
