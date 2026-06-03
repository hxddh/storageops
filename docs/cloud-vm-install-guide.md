# Cloud VM Install Guide

This guide is for first-time users installing StorageOps on a fresh Linux cloud
VM. It is based on a real Ubuntu cloud-host deployment and focuses on the parts
that commonly confuse new users: Python packaging, PyPI mirrors, model keys,
default model selection, and stale shell environment variables.

## What You Need

- SSH access to the VM.
- Python 3.11 or newer.
- Node.js 22.19 or newer (Pi 0.78+ requires Node >= 22.19).
- One model provider key. DeepSeek is used in the examples below.

Check the VM:

```bash
python3 --version
node --version
npm --version
```

If Node.js is missing, install it with your OS package manager or from
nodejs.org before continuing.

## 1. Install Pi Coding Agent

Pi Coding Agent is the runtime engine used by StorageOps.

```bash
npm install -g @earendil-works/pi-coding-agent
pi --version
```

StorageOps supports Pi `0.78.0` or newer. If an older Pi is already installed,
`storageops install` stops before deployment and prints the upgrade command.

## 2. Install StorageOps

Start with the normal PyPI install:

```bash
python3 -m pip install --upgrade storageops -i https://pypi.org/simple
```

On Ubuntu or Debian, system Python may reject global installs with
`externally-managed-environment`. Use a virtualenv, or if this is an isolated VM
where system-wide install is intentional:

```bash
python3 -m pip install --upgrade storageops --break-system-packages -i https://pypi.org/simple
```

Some cloud images use a regional PyPI mirror that may not have the latest
StorageOps release yet. If you see:

```text
No matching distribution found for storageops
```

install from the official PyPI index:

```bash
python3 -m pip install --upgrade storageops --break-system-packages -i https://pypi.org/simple
```

Verify the install:

```bash
storageops --version
```

If a just-published release is not picked up immediately, bypass local pip
cache while staying on the official PyPI index:

```bash
python3 -m pip install --upgrade storageops --break-system-packages --no-cache-dir -i https://pypi.org/simple
```

## 3. Deploy StorageOps Files

Use the default independent install. It writes to `~/.storageops/` and does not
modify an existing `~/.pi/` setup.

```bash
storageops install --force
```

The install step deploys files from the local Python package. It prints the
package version and package path before copying files, warns when PyPI has a
newer StorageOps release, and writes `~/.storageops/install.json`. If `pip`
failed or upgraded a different Python environment, this output makes the stale
package visible before the skills are redeployed.

It also prepares the optional HTTP trace helper used by `capture_http_trace`.
PyPI release packages include the verified Linux amd64 `httpmon` helper used by
common cloud VMs. During `storageops install`, StorageOps copies the matching
helper into `~/.storageops/bin/httpmon`; users do not need to install httpmon,
install Go, or edit `PATH`. Other supported platforms use the bounded download
fallback when the bundled helper does not match.

For upgrades, read the first three install lines before trusting the `[ok]`
summary:

```text
StorageOps package: v<latest>
Package path      : /usr/local/lib/python3.12/dist-packages/storageops_cli
Deploy target     : /root/.storageops/skills
```

`storageops install --force` does not upgrade the Python package. It only copies
the files bundled with the package already installed at `Package path`. If that
line still shows an older version, rerun the pip upgrade command first, then run
`storageops install --force` again.

Expected layout:

```text
~/.storageops/
├── agent/
│   ├── settings.json
│   ├── api-key
│   ├── extensions/storageops.ts
│   └── sessions/
├── bin/
│   └── httpmon
└── skills/
```

Check that skills are present:

```bash
find ~/.storageops/skills -maxdepth 1 -mindepth 1 -type d | wc -l
```

## 4. Configure A DeepSeek Key

For cloud VMs, the local key file is the least surprising option because it
belongs to the StorageOps agent directory and avoids shell startup-file drift.

```bash
mkdir -p ~/.storageops/agent
printf '%s\n' 'sk-...' > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
```

Do not paste real object-storage AK/SK credentials here. StorageOps needs a model
provider key for Pi, not cloud account credentials.

To confirm the file without printing the key:

```bash
key=$(tr -d '\r\n' < ~/.storageops/agent/api-key)
printf 'api-key len=%s suffix=%s\n' "${#key}" "${key: -4}"
ls -l ~/.storageops/agent/api-key
```

## 5. Set DeepSeek v4 Pro As The Default

If Pi has previously been used on the VM, `settings.json` may remember another
default model such as Claude. Set DeepSeek explicitly:

```bash
python3 - <<'PY'
import json
from pathlib import Path

p = Path.home() / ".storageops/agent/settings.json"
data = json.loads(p.read_text())
data["defaultProvider"] = "deepseek"
data["defaultModel"] = "deepseek-v4-pro"
p.write_text(json.dumps(data, indent=2) + "\n")
PY
```

Check the result:

```bash
cat ~/.storageops/agent/settings.json
```

Known-good DeepSeek models with Pi `0.78.0`:

```text
deepseek-v4-pro
deepseek-v4-flash
```

## 6. Run A Smoke Test

Use an explicit model first:

```bash
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
```

Then test the default:

```bash
storageops --print 'hello'
```

If both work, start an interactive session:

```bash
storageops
```

## Troubleshooting

### Default session uses Claude and returns 403

Symptom:

```text
Error: 403 {"error":{"type":"forbidden","message":"Request not allowed"}}
```

Likely cause: `~/.storageops/agent/settings.json` has an Anthropic default model,
but no Anthropic account or key is configured.

Check:

```bash
grep -E 'defaultProvider|defaultModel' ~/.storageops/agent/settings.json
```

Fix by setting:

```json
"defaultProvider": "deepseek",
"defaultModel": "deepseek-v4-pro"
```

Then restart `storageops`.

### DeepSeek returns 401 with an unexpected key suffix

Symptom:

```text
Error: 401 Authentication Fails, Your api key: ****xxxx is invalid
```

If `xxxx` is not the suffix of `~/.storageops/agent/api-key`, a shell
environment variable is overriding the key file.

Check current shell variables without printing the full key:

```bash
for v in DEEPSEEK_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY; do
  val="${!v-}"
  if [ -n "$val" ]; then
    printf '%s present len=%s suffix=%s\n' "$v" "${#val}" "${val: -4}"
  else
    printf '%s absent\n' "$v"
  fi
done
```

Check startup files:

```bash
grep -En 'DEEPSEEK_API_KEY|ANTHROPIC_API_KEY|OPENAI_API_KEY' \
  ~/.profile ~/.bashrc ~/.bash_profile ~/.zshrc 2>/dev/null
```

Remove stale entries or start StorageOps with clean key variables:

```bash
unset DEEPSEEK_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY
storageops
```

For a one-shot clean launch:

```bash
env -u DEEPSEEK_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY storageops --print 'hello'
```

If you were already inside an old interactive `storageops` session, exit it and
start a new one. Running processes keep the environment they had at launch time.

### `storageops install` says the API key is not configured

That message is a warning, not a failed install. Write the key file and retry a
smoke test:

```bash
printf '%s\n' 'sk-...' > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
```

### Confirm Which Processes Are Still Running

If errors still mention an old key suffix, an old `pi` process may still be
running:

```bash
ps -eo pid,ppid,etime,cmd | grep -E '(storageops|pi)( |$)' | grep -v grep
```

Exit the old terminal session or stop the old process, then launch StorageOps
again from a fresh shell.

### Upgrade Did Not Change The Skills

This usually means the Python package did not actually upgrade, even though
`storageops install --force` printed `[ok]`.

Check the installed package and deployed marker:

```bash
storageops --version
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / ".storageops/install.json"
print(p.read_text() if p.exists() else "missing install marker")
PY
```

On Ubuntu/Debian cloud hosts, use this repair sequence:

```bash
python3 -m pip install --upgrade storageops --break-system-packages --no-cache-dir -i https://pypi.org/simple
storageops install --force
storageops --version
```

Expected signs of success:

```text
Successfully installed storageops-<latest>
StorageOps package: v<latest>
[ok] install marker -> /root/.storageops/install.json
```

If the pip command fails with `externally-managed-environment`, the package was
not upgraded. If `storageops install --force` then runs, it will redeploy the old
bundled skills from the old package.

## Minimal Command Sequence

For a clean Ubuntu/Debian VM:

```bash
python3 --version
node --version
npm install -g @earendil-works/pi-coding-agent
python3 -m pip install --upgrade storageops --break-system-packages -i https://pypi.org/simple
storageops install --force
mkdir -p ~/.storageops/agent
printf '%s\n' 'sk-...' > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
python3 - <<'PY'
import json
from pathlib import Path
p = Path.home() / ".storageops/agent/settings.json"
data = json.loads(p.read_text())
data["defaultProvider"] = "deepseek"
data["defaultModel"] = "deepseek-v4-pro"
p.write_text(json.dumps(data, indent=2) + "\n")
PY
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
storageops
```
