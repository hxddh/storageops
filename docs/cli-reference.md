# CLI Reference

`storageops` is a thin wrapper around Pi Coding Agent.

## `storageops install`

```bash
storageops install [--merge] [--force]
```

Options:

| Option | Meaning |
| --- | --- |
| `--merge`, `-m` | Install into an existing `~/.pi/` Pi setup. |
| `--force`, `-f` | Reinstall files even when StorageOps already appears installed. |

Independent mode writes:

```text
~/.storageops/agent/settings.json
~/.storageops/agent/extensions/storageops.ts
~/.storageops/skills/
```

Merge mode writes:

```text
~/.pi/agent/settings.json
~/.pi/agent/extensions/storageops.ts
~/.pi/skills/
```

The installer backs up merged settings to `settings.json.storageops-backup`.

## `storageops --version`

```text
StorageOps v0.4.9  (pi: 0.78.0)
  独立安装: 是  (~/.storageops/agent)
  合并安装: 否  (~/.pi/agent)
```

## `storageops --help`

Prints install and launch help.

## Diagnosis Commands

All other arguments are passed to `pi` after setting `PI_CODING_AGENT_DIR`.

Examples:

```bash
storageops
storageops --print 'AccessDenied when reading bucket policy'
storageops --print @debug.log 'diagnose this rclone transfer'
storageops -c
storageops -r
```

Common Pi options:

| Option | Use |
| --- | --- |
| `--print`, `-p` | Non-interactive response. |
| `--provider <name>` | Select provider. |
| `--model <id>` | Select model. |
| `--api-key <key>` | Pass a model key for this run. |
| `--continue`, `-c` | Continue last session. |
| `--resume`, `-r` | Select a previous session. |
| `@file` | Include file contents as context. |

## API Keys

StorageOps injects provider keys from:

1. existing environment variables,
2. `{agent_dir}/auth.json`,
3. `{agent_dir}/api-key`.

Supported environment variables include:

```text
ANTHROPIC_API_KEY
DEEPSEEK_API_KEY
OPENAI_API_KEY
GEMINI_API_KEY
MISTRAL_API_KEY
GROQ_API_KEY
CEREBRAS_API_KEY
```

Object storage AK/SK credentials are not required for StorageOps diagnosis.
