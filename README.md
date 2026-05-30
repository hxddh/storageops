# StorageOps

[![CI](https://github.com/hxddh/storageops/actions/workflows/ci.yml/badge.svg)](https://github.com/hxddh/storageops/actions)

Autonomous diagnostic toolkit for S3-compatible object storage. Identifies root causes in access errors, throttling, lifecycle cost, FUSE mount hangs, TLS failures, and more — offline, no cloud connections required.

---

## Install

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops

# Rule-based diagnostics only (no dependencies)
pip install -e storageops-cli/

# LLM-powered agent with Anthropic Claude
pip install -e "storageops-cli/[llm]"

# LLM-powered agent with OpenAI
pip install -e "storageops-cli/[llm-openai]"

# Development (tests + linter)
pip install -e "storageops-cli/[dev]"
```

Requires Python ≥ 3.9.

---

## Configure

### API Key (for LLM agent)

Set one of the following (checked in priority order):

```bash
# Option 1: environment variable
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...

# Option 2: config file
mkdir -p ~/.storageops
cat > ~/.storageops/config.yaml << 'EOF'
llm_key: sk-ant-...         # Anthropic or OpenAI key
EOF

# Option 3: CLI flag (not recommended for scripts)
storageops agent mylog.log --llm-provider anthropic --llm-key sk-ant-...
```

The rule-based commands (`triage`, `analyze`, `report`) require no key.

---

## Quick Start

### 1 — Triage an error log (no key needed)

```bash
storageops triage error.log
```

Outputs: primary domain, confidence scores, missing evidence checklist.

### 2 — Run the LLM agent

```bash
storageops agent error.log --llm-provider anthropic
```

The agent runs a multi-turn ReAct loop: reads evidence → calls tools → reasons → produces a structured diagnostic report with root cause and remediation steps.

### 3 — Web UI

```bash
pip install -e "storageops-cli/[llm]" fastapi uvicorn
storageops serve
# Open http://localhost:8080
```

Three tabs: **Triage** (rule-based, no key), **Analyze** (domain-specific parsers), **Agent** (LLM, enter your key in the UI).

### 4 — MCP server (Claude Desktop)

```bash
pip install "mcp>=1.0"
storageops mcp
```

Add to `claude_desktop_config.json`:
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

---

## All Commands

| Command | What it does | Key needed? |
|---|---|---|
| `storageops triage <file>` | Classify domain, score confidence, list missing evidence | No |
| `storageops analyze <domain> <file>` | Run parser + analyzer for one domain | No |
| `storageops agent <file>` | Multi-turn LLM diagnostic agent | Yes (`--llm-provider`) |
| `storageops agent <file> --supervisor` | Multi-agent: triage → route → parallel specialists | Yes |
| `storageops agent <file> --interactive` | Follow-up questions after initial diagnosis | Yes |
| `storageops serve` | Start FastAPI server + web UI on :8080 | Optional |
| `storageops mcp` | Start MCP stdio server for Claude Desktop | No |
| `storageops memory list` | List past LLM diagnoses | No |
| `storageops memory search "ETag mismatch"` | BM25 search across past cases | No |
| `storageops audit list` | Show recent agent sessions with token counts | No |
| `storageops audit stats` | Aggregate token usage and tool frequency | No |
| `storageops eval --regression` | Check if triage confidence regressed vs last run | No |

### `storageops agent` options

```
--llm-provider  anthropic | openai | openai-compatible | ollama
--llm-model     Model name override (default: claude-opus-4-8 / gpt-4o)
--llm-key       API key (prefer env var)
--llm-base-url  Base URL for openai-compatible / ollama
--max-turns     Max agent turns (default: 8)
--verbose       Show tool calls and turn progress
--stream        Stream LLM output to stdout
--supervisor    Multi-agent supervisor mode
--interactive   Follow-up REPL after diagnosis
```

### `storageops analyze` domains

```
s3_protocol_compatibility   SigV4 errors, ETag mismatch, multipart issues
cli_sdk_behavior            rclone, s5cmd, AWS CLI, botocore errors
performance_throughput      Throttling (SlowDown/429), throughput, hot prefix
security_iam_policy         AccessDenied, IAM policy, cross-account, KMS
lifecycle_cost              Lifecycle rules, STANDARD_IA small-file penalty
mount_filesystem_workspace  FUSE mount hangs, git-on-S3 slowness
network_endpoint_access     VPC endpoints, DNS, TLS/SSL errors
```

---

## Supported LLM Providers

| Provider | `--llm-provider` | Package | Default model |
|---|---|---|---|
| Anthropic Claude | `anthropic` | `storageops-cli[llm]` | `claude-opus-4-8` |
| OpenAI | `openai` | `storageops-cli[llm-openai]` | `gpt-4o` |
| OpenAI-compatible (Deepseek, etc.) | `openai-compatible` | `storageops-cli[llm-openai]` | set `--llm-model` |
| Ollama (local) | `ollama` | none | set `--llm-model` |

**Ollama example:**
```bash
ollama pull llama3.1
storageops agent error.log \
  --llm-provider ollama \
  --llm-base-url http://localhost:11434 \
  --llm-model llama3.1
```

---

## Diagnostic Domains

| Domain | Typical evidence | Example root causes |
|---|---|---|
| `s3_protocol_compatibility` | XML error response, AWS debug log | Clock skew >5 min, multipart ETag mismatch |
| `cli_sdk_behavior` | rclone/s5cmd/aws CLI output | Wrong key path, ETag format mismatch, botocore bug |
| `performance_throughput` | Transfer timing, status code counts | Hot prefix throttling, small TCP window, single-threaded |
| `security_iam_policy` | 403 error text, policy JSON | Missing IAM allow, explicit Deny, cross-account gap |
| `lifecycle_cost` | Lifecycle XML, inventory CSV | Small-file IA penalty (<128 KB), minimum duration charges |
| `mount_filesystem_workspace` | dmesg, strace, mount command | FUSE timeout, vfs-cache-mode off, metadata storm |
| `network_endpoint_access` | curl -v, dig, openssl s_client | TLS cert expired, VPC route missing, DNS split-horizon |

---

## Examples

### Diagnose an rclone ETag mismatch

```bash
storageops agent rclone-debug.log --llm-provider anthropic --verbose
```

### Diagnose a 403 AccessDenied with policy review

```bash
storageops agent access-denied.log --llm-provider anthropic --max-turns 12
```

### Interactive follow-up session

```bash
storageops agent throttling.log \
  --llm-provider anthropic \
  --interactive
# After diagnosis, type follow-up questions at the prompt
```

### Rule-based triage (no key, instant)

```bash
storageops triage /var/log/aws-cli-debug.txt
# Output: primary domain + confidence scores + missing evidence
```

### Run golden case eval

```bash
python -m pytest storageops-cli/tests/ -v
```

---

## Architecture

```
agents/skills/          ← 10 SKILL.md files (diagnostic knowledge)
storageops-core/        ← 5 parsers + 5 analyzers + secret scanner
storageops-cli/         ← CLI, LLM agent, API server, MCP server
  └── storageops/
      ├── llm_agent.py       ReAct loop: reason → tool → observe → repeat
      ├── supervisor_agent.py Multi-agent: triage → route → specialists
      ├── tool_registry.py   12 tools (parse, analyze, generate, search)
      ├── llm_provider.py    Anthropic / OpenAI / Ollama abstraction
      ├── prompt_builder.py  System prompt = SKILL.md + safety rules
      ├── memory_store.py    BM25 case memory
      ├── audit_logger.py    JSONL session audit trail
      └── report_validator.py YAML frontmatter validator
```

**ReAct loop:**
```
Evidence → scan_secrets → search_memory → parse_* → analyze_* → report
                          │                                          │
                          └──────── critique turn ──────────────────┘
```

Each agent turn: LLM calls one tool → sees result → reasons → calls next tool.
After final answer, a critique prompt asks the LLM to self-review before committing.

---

## Safety

- **Secrets redacted** before evidence reaches the LLM (`scan_secrets` runs on input, tool results, and output)
- **Offline only** — no connections to cloud APIs, buckets, or IAM
- **Read-only** — remediation steps labeled `# manual-only:`, never executed
- **Unsafe output gate** — responses containing destructive patterns (delete bucket, make public, disable TLS) are blocked
- **Prompt injection defense** — user evidence wrapped in `<user_evidence>` XML tags; system prompt explicitly warns the LLM to ignore instruction-like content inside logs
- **Evidence-required** — all conclusions must cite tool output, not raw text

---

## Testing

```bash
# Full test suite (78 tests, offline)
python -m pytest storageops-cli/tests/ -v

# Core parsers and analyzers
python -m pytest storageops-core/tests/ -v

# Eval regression check (requires prior metrics run)
STORAGEOPS_EMIT_METRICS=1 python -m pytest storageops-cli/tests/
storageops eval --regression
```
