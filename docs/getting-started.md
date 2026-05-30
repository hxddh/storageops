# Getting Started

This guide walks through installation, configuration, and your first diagnosis — step by step.

---

## Step 1 — Check prerequisites

```bash
python3 --version   # must be 3.9 or later
pip --version
git --version
```

If any of these commands fail, install the missing tool before continuing.

---

## Step 2 — Install

```bash
# Clone the repository
git clone https://github.com/hxddh/storageops.git

# Enter the project directory
cd storageops

# Install with LLM support (includes both anthropic and openai packages)
pip install -e "storageops-cli/[llm]"

# Verify the install
storageops --help
```

Expected output:
```
usage: storageops [-h] {triage,analyze,report,eval,agent,audit,mcp,serve,memory} ...
```

If `storageops` is not found after installing, your pip's bin directory may not be on `PATH`.
Common fixes:
- In a virtual environment: activate it first (`source .venv/bin/activate`)
- Without a virtual environment: add `~/.local/bin` to your `PATH`

**Recommended: use a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e "storageops-cli/[llm]"
storageops --help
```

---

## Step 3 — Configure your API key

StorageOps uses your own LLM API key (BYOK — Bring Your Own Key). Keys are used only for calls to the LLM provider you choose; they are never sent anywhere else.

Export the environment variable for your provider:

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # Anthropic Claude  (recommended)
export OPENAI_API_KEY=sk-...             # OpenAI
export DEEPSEEK_API_KEY=sk-...           # DeepSeek
export MOONSHOT_API_KEY=sk-...           # Moonshot / Kimi
export DASHSCOPE_API_KEY=sk-...          # Qwen / Alibaba Cloud
export ZHIPU_API_KEY=...                 # Zhipu / GLM
export GROQ_API_KEY=gsk_...              # Groq
```

Set only one. StorageOps detects which provider to use from whichever env var is set.

**Make it permanent** by adding the export line to your shell profile:

```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc   # bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc    # zsh
```

**Alternative — config file** (persists across all shells without modifying profiles):

```bash
mkdir -p ~/.storageops
cat > ~/.storageops/config.yaml << 'EOF'
llm_key: sk-ant-...
EOF
chmod 600 ~/.storageops/config.yaml
```

**Key resolution order** (highest priority first):
1. `--llm-key` CLI flag
2. Provider-specific env var (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY`, `DASHSCOPE_API_KEY`, `ZHIPU_API_KEY`, `GROQ_API_KEY`)
3. `STORAGEOPS_LLM_KEY` generic env var
4. `~/.storageops/config.yaml` → `llm_key`

The rule-based commands (`triage`, `analyze`, `report`) require no key at all.

---

## Step 4 — Try the rule-based triage (no key needed)

Even without an API key, StorageOps can classify your evidence instantly:

```bash
storageops triage \
  agents/skills/storageops-eval-golden-cases/cases/throttling-hot-prefix/input/s3-access-log.txt
```

Expected output (abbreviated):
```json
{
  "ok": true,
  "primary_domain": "performance_throughput",
  "evidence_quality": "sufficient",
  "recommended_next_command": "storageops analyze performance_throughput ..."
}
```

---

## Step 5 — Run the LLM agent

The LLM agent does multi-turn reasoning: reads your evidence, calls diagnostic tools, forms hypotheses, and writes a structured report.

With your API key exported, the agent auto-detects the provider:

```bash
storageops agent \
  agents/skills/storageops-eval-golden-cases/cases/rclone-corrupted-transfer/input/rclone-debug.log
```

To watch the agent work turn by turn, add `--verbose`:

```bash
storageops agent \
  agents/skills/storageops-eval-golden-cases/cases/rclone-corrupted-transfer/input/rclone-debug.log \
  --verbose
```

You'll see the agent:
- **Turn 1**: Write an investigation plan and call `search_memory`
- **Turn 2**: Call `scan_secrets` to redact credentials
- **Turn 3**: Call `parse_rclone_log` to extract structured facts
- **Turn 4+**: Reason through the evidence and write the report

The final report is printed to stdout with a YAML frontmatter block:

```markdown
---
category: cli_sdk_behavior
root_cause_type: multipart_etag_format_mismatch
confidence: 0.92
severity: high
---

## Summary
rclone's multipart ETag format uses MD5-of-parts which doesn't match...

## Key Evidence
...

## Remediation
# manual-only: ...
```

**Override provider or model explicitly** if needed:

```bash
storageops agent error.log --llm-provider anthropic --llm-model claude-opus-4-8
storageops agent error.log --llm-provider openai --llm-model gpt-5.5
storageops agent error.log --llm-provider deepseek --llm-model deepseek-v4-pro
storageops agent error.log --llm-provider groq
```

---

## Step 6 — Use the web UI (optional)

```bash
pip install fastapi uvicorn
storageops serve
# Open http://localhost:8080
```

- **Triage tab**: Paste or drag-drop a log file → instant domain detection, no key needed
- **Analyze tab**: Select a domain, paste evidence → runs the rule-based parser pipeline
- **Agent tab**: Enter your API key, choose provider and model → full LLM diagnosis in the browser

---

## Common Workflows

### 403 access denied

```bash
storageops agent access-denied.log --max-turns 10
```

The agent checks memory for similar cases, scans for credentials, calls `analyze_policy` to trace the denial, and calls `generate_policy_fix` to output a policy statement (manual review before applying).

### Slow transfers — is it throttling?

```bash
storageops agent slow-transfer.log
```

The agent detects 429/SlowDown patterns and calls `detect_throttling` + `analyze_throughput`.

### rclone reports files corrupted after transfer

```bash
storageops agent rclone-debug.log
```

ETag mismatch from multipart uploads is the most common cause. Use `--verbose` to see the tool reasoning.

### Interactive follow-up after diagnosis

```bash
storageops agent error.log --interactive
```

After the initial report, enter a follow-up prompt:
- "What's the exact multipart threshold to set?"
- "Would this affect Tencent COS too?"
- "Show me the rclone mount options I should change"

### Complex multi-domain problems

```bash
storageops agent error.log --supervisor
```

Multi-agent mode: a triage agent classifies the evidence, then routes to one or two specialist agents.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'anthropic'` or `No module named 'openai'`

The LLM dependencies are not installed. Run:

```bash
pip install -e "storageops-cli/[llm]"
```

This installs both the `anthropic` and `openai` packages.

### `storageops: command not found`

pip installed the script but the bin directory is not on your PATH.

```bash
# Check where pip installs scripts
python3 -m site --user-base

# Add to PATH (bash)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Or use a virtual environment as described in Step 2.

### Agent exits immediately with no output

The provider could not be determined. Check which env var you've exported:

```bash
env | grep -E 'ANTHROPIC|OPENAI|DEEPSEEK|MOONSHOT|DASHSCOPE|ZHIPU|GROQ'
```

If nothing appears, export a key (see Step 3). Then retry:

```bash
storageops agent mylog.log --verbose
```

### "API key not found" error

The env var is set in a different shell or not exported. Verify:

```bash
echo $ANTHROPIC_API_KEY   # should print your key (not empty)
```

If empty, re-export in the current terminal or add to your shell profile.

### Agent report shows `report_valid: false`

The LLM didn't include the required YAML frontmatter. Increase `--max-turns`:

```bash
storageops agent mylog.log --max-turns 12
```

### `pip install` fails with permission error

Use `--user` flag or a virtual environment:

```bash
pip install --user -e "storageops-cli/[llm]"
# or
python3 -m venv .venv && source .venv/bin/activate
pip install -e "storageops-cli/[llm]"
```

---

## Next Steps

- **[CLI Reference](cli-reference.md)** — full documentation of every command and flag
- **[Architecture Guide](../CLAUDE.md)** — internals: ReAct loop, tool registry, skill loading
