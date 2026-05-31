# StorageOps

[![CI](https://github.com/hxddh/storageops/actions/workflows/ci.yml/badge.svg)](https://github.com/hxddh/storageops/actions)

Autonomous diagnostic agent for S3-compatible object storage. Give it a log file or error output — it reasons through the evidence with multi-turn tool calls and writes a structured report with root cause and remediation steps. Works entirely offline; no cloud connections required.

---

## Prerequisites

Before you start, verify these are installed:

```bash
python3 --version   # must be 3.9 or later
pip --version
git --version
```

You will also need an API key from one of the supported LLM providers listed below. (The rule-based `triage` command works without any key.)

---

## Install

```bash
# Step 1 — clone the repository
git clone https://github.com/hxddh/storageops.git

# Step 2 — enter the project directory
cd storageops

# Step 3 — install with LLM support
pip install -e "storageops-cli/[llm]"

# Step 4 — verify
storageops --help
```

You should see:
```
usage: storageops [-h] {triage,analyze,report,eval,agent,audit,mcp,serve,memory} ...
```

> **Tip:** Use a virtual environment to avoid dependency conflicts:
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate    # Windows: .venv\Scripts\activate
> pip install -e "storageops-cli/[llm]"
> ```

---

## Upgrade

```bash
# Step 1 — pull the latest code (inside the storageops directory)
cd storageops
git pull origin main

# Step 2 — reinstall to pick up any new dependencies
pip install -e "storageops-cli/[llm]"

# Step 3 — verify
storageops --version 2>/dev/null || storageops --help | head -1
```

If you used a virtual environment, activate it before running `pip install`.

> **What changes with each upgrade:**
> - New providers, model defaults, and diagnostic rules take effect immediately after `git pull`
> - New Python dependencies (if any) require the `pip install` step
> - Your past diagnoses in `~/.storageops/memory.jsonl` and audit log are never touched by an upgrade

---

## Configure

Export the API key for whichever LLM provider you use. StorageOps auto-detects the provider from the environment variable — no other flags needed.

```bash
# Set exactly one of these:
export ANTHROPIC_API_KEY=sk-ant-...     # Anthropic Claude  (recommended)
export OPENAI_API_KEY=sk-...            # OpenAI
export DEEPSEEK_API_KEY=sk-...          # DeepSeek
export MOONSHOT_API_KEY=sk-...          # Moonshot / Kimi
export DASHSCOPE_API_KEY=sk-...         # Qwen / Alibaba Cloud
export ZHIPU_API_KEY=...                # Zhipu / GLM
export GROQ_API_KEY=gsk_...             # Groq  (free tier available)
```

To make this permanent across terminal sessions, add the `export` line to `~/.bashrc` or `~/.zshrc`.

---

## Run

```bash
storageops agent /path/to/your/error.log
```

The agent detects your provider from the environment variable, reads the log, calls diagnostic tools, reasons through the evidence, and prints a structured report:

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

| Provider | Set this env var | Default model |
|---|---|---|
| Anthropic Claude | `ANTHROPIC_API_KEY` | `claude-opus-4-8` |
| OpenAI | `OPENAI_API_KEY` | `gpt-5.5` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-v4-pro` |
| Moonshot / Kimi | `MOONSHOT_API_KEY` | `kimi-k2.6` |
| Qwen / Alibaba Cloud | `DASHSCOPE_API_KEY` | `qwen3-max` |
| Zhipu / GLM | `ZHIPU_API_KEY` | `glm-5.1` |
| Groq | `GROQ_API_KEY` | `meta-llama/llama-4-scout-17b-16e-instruct` |
| Ollama (local, no key) | — | `llama3.3` |

**Override model or provider** at runtime with flags:
```bash
storageops agent error.log --llm-provider deepseek --llm-model deepseek-v3
```

**Ollama (local models, no API key required):**
```bash
ollama pull llama3.3
storageops agent error.log --llm-provider ollama --llm-model llama3.3
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

The agent automatically routes to the right specialist based on the evidence:

| Domain | What it diagnoses |
|---|---|
| `s3_protocol_compatibility` | SigV4 errors, clock skew, ETag mismatch, multipart upload |
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

  --llm-provider    anthropic | openai | deepseek | moonshot | qwen | zhipu | groq | ollama | openai-compatible
                    Default: auto-detected from env var (see Configure above)
  --llm-model       Override the default model for the selected provider
  --llm-key         API key — set env var instead wherever possible
  --llm-base-url    Base URL for Ollama or a custom endpoint
  --max-turns N     Max reasoning turns (default: 8; use 12 for complex cases)
  --verbose         Print each tool call and result as the agent works
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
