# Getting Started

This guide walks you from installation to your first LLM-powered diagnosis in under 10 minutes.

---

## Step 1: Install

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops

# Install with Anthropic LLM support
pip install -e "storageops-cli/[llm]"

# Verify
storageops --help
```

You should see:
```
usage: storageops [-h] {triage,analyze,report,eval,agent,audit,mcp,serve,memory} ...
```

---

## Step 2: Configure your API key

StorageOps uses your own LLM API key (BYOK — Bring Your Own Key). The key never leaves
your machine except for calls to the LLM provider you choose.

```bash
# Recommended: set an environment variable
export ANTHROPIC_API_KEY=sk-ant-...     # for Anthropic Claude
export OPENAI_API_KEY=sk-...            # for OpenAI

# Alternative: config file (persists across sessions)
mkdir -p ~/.storageops
cat > ~/.storageops/config.yaml << 'EOF'
llm_key: sk-ant-...
EOF
chmod 600 ~/.storageops/config.yaml
```

**Key resolution order** (highest priority wins):
1. `--llm-key` CLI flag
2. `ANTHROPIC_API_KEY` or `STORAGEOPS_LLM_KEY` environment variable
3. `~/.storageops/config.yaml` → `llm_key`

The rule-based commands (`triage`, `analyze`, `report`) require no key at all.

---

## Step 3: Try the rule-based triage (no key needed)

Even without an API key, StorageOps can classify your evidence instantly:

```bash
# Using a golden case as example
storageops triage \
  agents/skills/storageops-eval-golden-cases/cases/throttling-hot-prefix/input/s3-access-log.txt
```

Expected output:
```json
{
  "ok": true,
  "primary_domain": "performance_throughput",
  "all_domains": ["performance_throughput"],
  "scores": {"performance_throughput": 0.55},
  "evidence_quality": "partial",
  ...
}
```

---

## Step 4: Run the LLM agent

The LLM agent does multi-turn reasoning: it reads your evidence, calls diagnostic tools,
forms hypotheses, and writes a structured report.

```bash
storageops agent \
  agents/skills/storageops-eval-golden-cases/cases/rclone-corrupted-transfer/input/rclone-debug.log \
  --llm-provider anthropic \
  --verbose
```

Watch the agent:
- **Turn 1**: Write an investigation plan, call `search_memory`
- **Turn 2**: Call `scan_secrets` to redact credentials
- **Turn 3**: Call `parse_rclone_log` to extract structured facts
- **Turn 4+**: Reason about results and write a report

The final report is printed to stdout in Markdown with a YAML frontmatter block:
```markdown
---
category: cli_sdk_behavior
root_cause_type: multipart_etag_format_mismatch
confidence: 0.92
severity: high
---

## Summary
rclone's multipart ETag format uses MD5-of-parts which doesn't match...
```

---

## Step 5: Use the web UI

```bash
pip install fastapi uvicorn
storageops serve
# Open http://localhost:8080
```

**Triage tab**: Paste a log or drag-drop a file → instant domain detection, no key needed.

**Analyze tab**: Select a domain, paste evidence → runs the rule-based parser pipeline.

**Agent tab**: Enter your API key, provider, and model → runs the full LLM agent in the browser.

---

## Common Workflows

### "I have a 403 error log"

```bash
storageops agent access-denied.log \
  --llm-provider anthropic \
  --max-turns 10
```

The agent will:
1. Check memory for similar 403 cases
2. Scan for exposed credentials in your log
3. Call `parse_awscli_debug` or `analyze_policy` to trace the denial
4. Call `generate_policy_fix` to output a policy statement to add (manual review)

### "Transfers are slow — is it throttling?"

```bash
storageops agent slow-transfer.log \
  --llm-provider anthropic
```

The agent detects 429/SlowDown patterns and calls `detect_throttling` + `analyze_throughput`.

### "rclone says files are corrupted after transfer"

```bash
storageops agent rclone-debug.log \
  --llm-provider anthropic
```

ETag mismatch from multipart uploads is the most common cause. The agent knows this.

### "Follow up after the initial diagnosis"

```bash
storageops agent error.log \
  --llm-provider anthropic \
  --interactive
```

After the initial report, you get a follow-up prompt. Ask questions like:
- "What's the exact multipart threshold to set?"
- "Would this affect Tencent COS too?"
- "Show me the rclone mount options I should change"

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'anthropic'`
```bash
pip install -e "storageops-cli/[llm]"
```

### `ModuleNotFoundError: No module named 'openai'`
```bash
pip install -e "storageops-cli/[llm-openai]"
```

### Agent exits immediately with no output
Run with `--verbose` to see what's happening:
```bash
storageops agent mylog.log --llm-provider anthropic --verbose
```

### "API key not found"
Check key resolution order. The quickest fix:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
storageops agent mylog.log --llm-provider anthropic
```

### Agent produces a report with `report_valid: false`
The LLM didn't include the required YAML frontmatter. Try increasing `--max-turns`:
```bash
storageops agent mylog.log --llm-provider anthropic --max-turns 12
```

---

## Next Steps

- **[CLI Reference](cli-reference.md)** — full documentation of all commands and flags
- **[Architecture Guide](../CLAUDE.md)** — internals: ReAct loop, tool registry, skill loading
- **[Example walkthrough](examples/end-to-end-rclone-corrupted-transfer.md)** — step-by-step rclone diagnosis
