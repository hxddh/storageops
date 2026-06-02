# Getting Started

This guide gets StorageOps installed and running with Pi Coding Agent.

## 1. Prerequisites

- Python 3.11 or newer.
- Node.js 18 or newer (required by Pi Coding Agent).
- A model provider key: DeepSeek, Anthropic, or OpenAI.

Verify your environment:

```bash
python3 --version   # need 3.11+
node --version      # need 18+
```

Pi Coding Agent is installed automatically by `storageops install` if it is not
already present. To install it manually:

```bash
npm install -g @earendil-works/pi-coding-agent
pi --version
```

StorageOps warns (but does not auto-upgrade) when Pi is older than `0.78.0`, to
avoid disrupting existing Pi configurations.

## 2. Install StorageOps

```bash
pip install storageops
storageops install
```

> **Ubuntu / Debian:** If `pip install` fails with "externally-managed-environment",
> use `pip install storageops --break-system-packages` or activate a virtualenv first.

The default install is independent and writes to `~/.storageops/`, leaving `~/.pi/` alone.
`storageops install` automatically installs Pi Coding Agent via npm if it is not already present.

To merge into an existing Pi setup:

```bash
storageops install --merge
```

## 3. Configure a Model Key

Recommended:

```bash
export DEEPSEEK_API_KEY=sk-...
```

Other supported environment variables include:

```bash
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
```

Local file option:

```bash
echo sk-... > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
```

## 4. Run a Diagnosis

Single-shot:

```bash
storageops --print 's5cmd sync returns 429 SlowDown; diagnose the likely bottleneck'
```

With a log file:

```bash
storageops --print @/path/to/rclone-debug.log 'explain this transfer checksum failure'
```

Interactive:

```bash
storageops
```

## 5. Update

```bash
pip install --upgrade storageops
storageops install --force
```

Use `--merge --force` if you intentionally maintain a merged `~/.pi/` install.

## 6. Validate a Checkout

```bash
python3 scripts/skill_integrity_check.py
python3 skills/storageops-eval-golden-cases/scripts/golden_case_validator.py \
  skills/storageops-eval-golden-cases/cases
make validate
```

## Troubleshooting

If `storageops` says it is not installed, run `storageops install`.

If Pi cannot find skills, check:

```bash
storageops --version
cat ~/.storageops/agent/settings.json
ls ~/.storageops/skills
```

If model calls fail, verify your provider key is visible in the same shell:

```bash
env | grep -E 'DEEPSEEK|ANTHROPIC|OPENAI'
```
