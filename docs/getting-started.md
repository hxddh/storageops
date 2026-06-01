# Getting Started

This guide walks through installation, setup, and your first diagnosis.

---

## Step 1 — Install

```bash
pip install storageops
```

If `storageops` is not found after install, add pip's bin directory to PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

Or use a virtual environment:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install storageops
```

---

## Step 2 — Run setup

```bash
storageops setup
```

This downloads Pi Coding Agent and asks for your API key. Paste your key — provider
is auto-detected from the prefix (`sk-ant-` → Anthropic, `sk-` → OpenAI). That's it.

---

## Step 3 — Start a session

```bash
storageops
```

Type your problem in plain language and press Enter. Type `/` to see all commands.

```
StorageOps  anthropic  ·  type / for commands  ·  Ctrl+C to interrupt  ·  /exit to quit
  Session  a3f2b1c8

> Got 403 from boto3 on GetObject, but my IAM role has s3:GetObject
```

Reference a local file by prefixing with `@`:

```
> here's the error trace @/var/log/s3-error.log
```

### Slash commands

| Command | Action |
|---------|--------|
| `/help` | Show available commands |
| `/resume` | Pick a past session to continue |
| `/clear` | Start a fresh session |
| `/status` | Show session ID, Pi and API key status |
| `/config` | View or change configuration |
| `/memory` | Browse past diagnosed cases |
| `/update` | Download latest Pi binary and reinstall skills |
| `/doctor` | Check environment health |
| `/setup` | Re-run setup (API key, Pi install) |
| `/verbose` | Toggle verbose output (shows tool calls) |
| `/exit` | Quit |

Sessions are saved automatically to `~/.storageops/sessions/`.

---

## Common Workflows

### 403 access denied

```bash
storageops
> s3://my-bucket/data/file.csv — AccessDenied, but my IAM role has s3:GetObject
```

### Slow transfers — is it throttling?

```bash
storageops < slow-transfer.log
```

### Capture wire-level traffic with httpmon

Wrap any storage command with [httpmon](https://github.com/hxddh/https-traffic-inspector)
to give StorageOps full HTTP evidence:

```bash
httpmon --format json aws s3 cp s3://bucket/key . 2>&1 | storageops
```

### Multi-turn investigation

Add evidence progressively across turns — context accumulates:

```
> access denied on GetObject
> here's my bucket policy: @policy.json
> and the IAM role: @role.json
```

---

## Configuration

Inside a session:
```
/config                          # show current config
/config set provider openai      # change provider
/config set api_key sk-...       # set API key
```

Config is stored at `~/.storageops/config.json`.

---

## Offline triage (no API key needed)

Rule-based triage works without Pi or an API key:

```bash
storageops triage error.log
storageops analyze security_iam_policy policy.json
storageops scan logs/*.log
```

---

## Troubleshooting

### `storageops: command not found`

```bash
python3 -m site --user-base          # shows e.g. /home/you/.local
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

### Pi not found

Run `/setup` inside a session, or `storageops setup` at the terminal.

### API key missing or wrong

Use `/config set api_key sk-...` inside a session, or `storageops setup` to re-configure.

---

## Next Steps

- **[CLI Reference](cli-reference.md)** — all commands, flags, and output formats
- **[Architecture Guide](../ARCHITECTURE.md)** — tool registry, skill loading, Pi RPC internals
