# Getting Started

This guide walks through installation, setup, and your first diagnosis — step by step.

---

## Step 1 — Check prerequisites

```bash
python3 --version   # 3.10 or later required
pip --version
```

---

## Step 2 — Install

```bash
pip install storageops
```

Verify:

```bash
storageops --help
```

If `storageops` is not found, your pip bin directory may not be on `PATH`:

```bash
# Common fix for user installs
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**Recommended: use a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install storageops
storageops --help
```

---

## Step 3 — Run setup

```bash
storageops setup
```

The setup wizard:
1. Downloads Pi Coding Agent automatically.
2. Asks which LLM provider to use (Anthropic or OpenAI).
3. Asks for your API key and saves it to `~/.storageops/config.json`.

After setup, check that everything is healthy:

```bash
storageops doctor
```

---

## Step 4 — Try offline triage (no API key needed)

Rule-based triage works instantly without any API key:

```bash
storageops triage \
  agents/skills/storageops-eval-golden-cases/cases/throttling-hot-prefix/input/s3-access-log.txt
```

Expected output:
```
Domain:  performance_throughput  (0.72)
Evidence quality: sufficient
Recommended: storageops analyze performance_throughput <file>
```

---

## Step 5 — Start the interactive REPL

```bash
storageops
```

Describe your issue in plain language. Press Enter to submit. Context accumulates across turns.

```
StorageOps  anthropic  ·  type / for commands  ·  Ctrl+C to interrupt  ·  /exit to quit
  Session  a3f2b1c8

> Got 403 from boto3 on GetObject, but my IAM role has s3:GetObject
```

**Reference a local file:**
```
> here's the error trace @/var/log/s3-error.log
```

**Slash commands:**

| Command | Action |
|---------|--------|
| `/help` | Show available commands |
| `/clear` | Start a fresh session |
| `/status` | Show session ID, Pi and API key status |
| `/doctor` | Check environment health |
| `/setup` | Re-run setup wizard |
| `/verbose` | Toggle verbose output (shows tool calls) |
| `/exit` | Quit |

---

## Step 6 — Resume a session

Sessions are saved automatically to `~/.storageops/sessions/`. To pick up where you left off:

```bash
storageops resume            # pick from recent sessions
storageops resume abc12345   # resume by session ID
```

---

## Common Workflows

### 403 access denied

```bash
storageops
> s3://my-bucket/data/file.csv — AccessDenied, but my IAM role has s3:GetObject
```

The agent checks memory for similar cases, calls `analyze_policy` to trace the denial,
and `generate_policy_fix` to output a corrected policy statement.

### Slow transfers — is it throttling?

```bash
storageops < slow-transfer.log
```

The agent detects 429/SlowDown patterns and calls `detect_throttling` + `analyze_throughput`.

### Capture wire-level traffic with httpmon

Wrap any storage command with [httpmon](https://github.com/hxddh/https-traffic-inspector)
to give StorageOps full HTTP evidence:

```bash
httpmon --format json aws s3 cp s3://bucket/key . 2>&1 | storageops
```

### One-shot pipe

```bash
aws s3 cp s3://bucket/key . 2>&1 | storageops
cat rclone-debug.log | storageops
```

---

## Manage configuration

```bash
storageops config list              # show current config
storageops config set provider openai
storageops config set api_key sk-...
storageops config get api_key       # prints [REDACTED]
```

Config is stored at `~/.storageops/config.json`.

---

## Update

```bash
storageops update           # download latest Pi + reinstall skills
storageops update --check   # check without installing
```

---

## Troubleshooting

### `storageops: command not found`

pip installed the script but the bin directory is not on your PATH.

```bash
python3 -m site --user-base          # shows e.g. /home/you/.local
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Or use a virtual environment.

### `storageops doctor` shows Pi not found

Run `storageops setup` to download Pi, or verify that `pi` is on your PATH.

### REPL returns "Pi is not available"

1. Run `storageops setup` to (re-)install Pi.
2. Ensure your API key is set: `storageops config list`.
3. Check health: `storageops doctor`.

### report shows `report_valid: false`

The agent didn't include required YAML frontmatter. Try `diagnose` with a longer timeout:

```bash
storageops diagnose mylog.log --max-turns 12
```

---

## Next Steps

- **[CLI Reference](cli-reference.md)** — full documentation of every command and flag
- **[Tutorial](tutorial.md)** — worked examples for common S3 problems
- **[Architecture Guide](../ARCHITECTURE.md)** — internals: tool registry, skill loading, Pi RPC
