# Getting Started

This guide gets StorageOps installed and running with Pi Coding Agent.

For a step-by-step Linux cloud VM walkthrough with DeepSeek setup and common
401/403 fixes, see [Cloud VM Install Guide](cloud-vm-install-guide.md).

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

StorageOps stops before deployment when Pi is older than `0.78.0` and prints the
manual upgrade command, avoiding both auto-upgrades and half-ready installs.

## 2. Install StorageOps

```bash
python3 -m pip install storageops -i https://pypi.org/simple
storageops install
```

> **Ubuntu / Debian:** If `pip install` fails with "externally-managed-environment",
> use `python3 -m pip install storageops --break-system-packages -i https://pypi.org/simple`
> on an isolated VM, or activate a virtualenv first.
>
> **Cloud or regional PyPI mirrors:** If your default mirror reports
> "No matching distribution found for storageops", install from the official
> PyPI index:
>
> ```bash
> python3 -m pip install --upgrade storageops -i https://pypi.org/simple
> ```

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

StorageOps reads this local key file and exposes the key to Pi for the selected
agent directory. You normally do not need to pass `--api-key` on each command.

## 4. Run a Diagnosis

DeepSeek smoke test:

```bash
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
```

`deepseek-v4-pro` and `deepseek-v4-flash` are known-good DeepSeek model choices
with Pi 0.78.0.

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
python3 -m pip install --upgrade storageops -i https://pypi.org/simple
storageops install --force
```

Use `--merge --force` if you intentionally maintain a merged `~/.pi/` install.
`storageops install --force` deploys the files bundled in the currently installed
local package; it does not run `pip upgrade` for you. The installer prints the
local package version and path, warns when PyPI has a newer version, and writes
`~/.storageops/install.json` for troubleshooting.

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

If you use the local key file instead of environment variables, check its path
and permissions:

```bash
ls -l ~/.storageops/agent/api-key
```

If DeepSeek returns a model-name error, retry with a known-good model:

```bash
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
```

## Cloud VM Minimal Check

This sequence mirrors a clean Ubuntu/Debian cloud host:

```bash
python3 --version
node --version
npm install -g @earendil-works/pi-coding-agent
python3 -m pip install --upgrade storageops --break-system-packages -i https://pypi.org/simple
storageops install --force
echo sk-... > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
```
