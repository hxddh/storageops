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
StorageOps v0.4.17  (pi: 0.78.0)
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
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
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

The local `api-key` file is intended for the selected StorageOps/Pi agent
directory, for example `~/.storageops/agent/api-key` in independent mode. When
it is present, StorageOps exposes the key to Pi before launching the agent; users
do not need to pass `--api-key` for normal commands.

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

DeepSeek examples:

```bash
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
storageops --provider deepseek --model deepseek-v4-flash --print 'hello'
```

If DeepSeek rejects a model name, retry with one of the known-good model ids
above.
