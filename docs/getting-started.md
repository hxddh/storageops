# Getting Started

## Step 1 — Install Pi Coding Agent

StorageOps runs on top of Pi Coding Agent. Install Pi first:

```bash
curl -fsSL https://raw.githubusercontent.com/hxddh/storageops/main/scripts/install-pi.sh | bash
```

Or install Pi manually:

```bash
npm install -g @earendil-works/pi-coding-agent
```

## Step 2 — Install StorageOps

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
pip install -e .   # thin CLI shim (optional)
```

This gives you the `storageops` command which forwards to `pi` with StorageOps skills loaded.

## Step 3 — Start a session

```bash
storageops
```

Or directly with Pi:

```bash
pi --skills ./skills
```

## Step 4 — Describe your issue

Just type naturally:

```
> I'm getting 429 SlowDown errors with s5cmd sync. Here's the log: [paste log]
> My rclone mount keeps dropping with "corrupted on transfer" for files > 100MB
> DNS resolution is failing for my VPC endpoint — nslookup shows NXDOMAIN
```

The AI agent will:
1. Call `scan_secrets` to redact any credentials
2. Call `detect_domain` to classify the issue
3. Activate the appropriate skill pack(s)
4. Diagnose root cause and provide recommendations

## Slash commands (in REPL)

During an interactive session, you can use Pi's slash commands:

| Command | Description |
|---------|-------------|
| `/editor` | Open editor to write long prompts |
| `/view` | View last report in pager |
| `/history` | Show command history |
| `/exit` | Quit session |

## Next Steps

- Read the [Tutorial](tutorial.md) for scenario walkthroughs
- See the [Quick Reference](quick-reference.md) for one-line reference
- Read the [CLI Reference](cli-reference.md) for advanced usage
