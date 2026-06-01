# Getting Started

This guide gets StorageOps installed and running with Pi Coding Agent.

## 1. Prerequisites

- Python 3.11 or newer.
- Pi Coding Agent available as `pi`.
- Node.js supported by your Pi installation.
- A model provider key for Pi, such as DeepSeek, Anthropic, or OpenAI.

Check Pi:

```bash
pi --version
```

StorageOps warns when Pi is older than `0.78.0`.

## 2. Install StorageOps

```bash
pip install storageops
storageops install
```

The default install is independent and writes to `~/.storageops/`, leaving `~/.pi/` alone.

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
