# StorageOps

[![CI](https://github.com/hxddh/storageops/actions/workflows/ci.yml/badge.svg)](https://github.com/hxddh/storageops/actions)

Autonomous diagnostic agent for S3-compatible object storage. Identifies root causes in access errors, throttling, lifecycle cost, FUSE mount hangs, TLS failures, and more — offline, no cloud connections.

---

## Quickstart

```bash
# 1. Install
pip install -e "storageops-cli/[llm]"

# 2. Set your API key (pick any one provider)
export ANTHROPIC_API_KEY=sk-ant-...   # Claude
export OPENAI_API_KEY=sk-...          # GPT-4o
export DEEPSEEK_API_KEY=sk-...        # DeepSeek
export MOONSHOT_API_KEY=sk-...        # Moonshot / Kimi
export DASHSCOPE_API_KEY=sk-...       # Qwen / Alibaba Cloud
export ZHIPU_API_KEY=...              # Zhipu / GLM
export GROQ_API_KEY=gsk_...           # Groq

# 3. Diagnose
storageops agent error.log
```

Provider is auto-detected from the env var you set — no extra flags needed.

---

## Supported Providers

| Provider | Env var | Default model |
|---|---|---|
| Anthropic Claude | `ANTHROPIC_API_KEY` | claude-opus-4-8 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat |
| Moonshot / Kimi | `MOONSHOT_API_KEY` | moonshot-v1-8k |
| Qwen / Alibaba | `DASHSCOPE_API_KEY` | qwen-max |
| Zhipu / GLM | `ZHIPU_API_KEY` | glm-4-plus |
| Groq | `GROQ_API_KEY` | llama-3.3-70b-versatile |
| Ollama (local) | *(none)* | llama3.2 |
| Custom OpenAI-compatible | `STORAGEOPS_LLM_KEY` | set `--llm-model` |

---

## What it does

The agent runs a multi-turn ReAct loop on your evidence file:

```
scan_secrets → search_memory → parse logs → analyze → critique → report
```

Final output is a structured Markdown report:

```markdown
---
category: cli_sdk_behavior
root_cause_type: multipart_etag_format_mismatch
confidence: 0.92
severity: high
---

## Summary
rclone's multipart ETag format doesn't match the server's expected format...

## Key Evidence
- parse_rclone_log: ETag mismatch on all parts > 5 MB
- rclone v1.64.2, AWS S3, --s3-upload-cutoff not set

## Remediation
# manual-only: add to rclone.conf:
[s3-remote]
s3_upload_cutoff = 200Mi
```

---

## All 7 diagnostic domains

| Domain | What it diagnoses |
|---|---|
| `s3_protocol_compatibility` | SigV4 errors, clock skew, ETag mismatch, multipart |
| `cli_sdk_behavior` | rclone, s5cmd, AWS CLI, botocore errors |
| `performance_throughput` | Throttling (SlowDown/429), hot prefix, slow transfers |
| `security_iam_policy` | 403 AccessDenied, IAM/bucket policy, KMS, cross-account |
| `lifecycle_cost` | Lifecycle rules, STANDARD_IA small-file penalty |
| `mount_filesystem_workspace` | FUSE mount hangs, git-on-S3 slowness |
| `network_endpoint_access` | VPC endpoints, DNS, TLS/SSL certificate errors |

---

## Options

```
storageops agent <file> [options]

  --llm-provider    Override auto-detected provider
  --llm-model       Override default model
  --llm-key         API key (prefer env var)
  --llm-base-url    Base URL for ollama / custom endpoint
  --max-turns       Max agent turns (default: 8)
  --verbose         Show tool calls and turn progress
  --stream          Stream output to stdout
  --supervisor      Multi-agent mode (triage → route → specialists)
  --interactive     Follow-up REPL after diagnosis
```

**Ollama (local model):**
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

## Other commands

```bash
# Rule-based triage (no key needed, instant)
storageops triage error.log

# Web UI
storageops serve          # → http://localhost:8080

# MCP server for Claude Desktop
storageops mcp

# Search past diagnoses
storageops memory search "ETag mismatch"

# View session history + token usage
storageops audit list
storageops audit stats
```

---

## Testing

```bash
python -m pytest storageops-cli/tests/ -q   # 78 tests, offline
```

---

## Safety

Secrets are redacted before evidence reaches the LLM. All recommendations are labeled `# manual-only:` — the agent never modifies cloud resources. See [CLAUDE.md](CLAUDE.md) for architecture details.
