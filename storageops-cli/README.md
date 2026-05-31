# StorageOps CLI

The StorageOps CLI wraps deterministic `storageops-core` parsers/analyzers, the interactive
REPL, and the Pi Coding Agent runtime.

## Install

```bash
pip install storageops
storageops setup    # download Pi, select provider, enter API key
```

## Interactive REPL (recommended)

```bash
storageops
```

Describe your problem in plain language. The agent routes to the correct skill automatically.

```
> s3://my-bucket/data/file.csv — AccessDenied, but my IAM role has s3:GetObject
```

Reference a local file:
```
> analyze this log @/var/log/s3-error.log
```

Resume a previous session:
```bash
storageops resume            # pick from recent sessions
storageops resume abc12345   # resume by session ID
```

## Agent Runtime

`storageops diagnose <file>` (and the REPL) use **Pi Coding Agent**. StorageOps does not
manage LLM providers, API keys, base URLs, or model registries — configure those in Pi.

```bash
storageops diagnose ./examples/rclone-etag-mismatch.log
storageops diagnose ./examples/s5cmd-429.log --stream
storageops diagnose evidence.log --pi-model claude-opus-4-8
```

If Pi is missing, run `storageops setup` to install it.

## Configuration

```bash
storageops config list                    # show config
storageops config set provider anthropic
storageops config set api_key sk-ant-...
```

Config stored at `~/.storageops/config.json`.

## Non-Agent Commands (No Pi Required)

### `triage`

```bash
storageops triage <evidence-file>
storageops triage error.log --format json
```

Classifies evidence, assesses confidence, runs secret scanning, and suggests the next command.

### `analyze`

```bash
storageops analyze <domain> <evidence-file>
storageops analyze security_iam_policy policy.json
storageops analyze performance_throughput s3-access.log
```

Runs the domain-specific offline parser/analyzer. `storageops-core` stays independent of Pi.

### `scan`

```bash
storageops scan logs/*.log --output report.md
```

Triage multiple files at once. (`batch` is a hidden alias.)

### `report`

```bash
storageops report <analysis-json>
```

Renders an analysis JSON file as Markdown.

### `eval`

```bash
storageops eval --all
storageops eval --case rclone-corrupted-transfer
```

Runs golden case evaluation without calling real LLM APIs.

## Update

```bash
storageops update           # download latest Pi + reinstall skills
storageops update --check   # check without installing
```

## Safety

StorageOps is offline and read-only. It never needs real object storage credentials,
redacts evidence before Pi sees it, and validates Pi output before printing a report.
Mutating remediation commands are labeled `manual-only`.
