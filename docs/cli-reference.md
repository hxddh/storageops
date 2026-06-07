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
Before copying files, it prints the local StorageOps package version, package
path, and deploy target. It also makes a best-effort PyPI version check; when a
newer release exists, the installer warns that `--force` would redeploy files
from the older local package. Deployment provenance is written to
`~/.storageops/install.json`.

## `storageops --version`

```text
StorageOps v0.4.57  (pi: 0.78.0)
  httpmon             : /root/.storageops/bin/httpmon
  api key             : api-key file
  independent install : yes  (~/.storageops/agent)
  merged install      : no   (~/.pi/agent)
```

The `api key` line reports where a key is configured — environment variable,
the `api-key` file, or `auth.json` — i.e. the same sources the launcher reads,
so it stays accurate when the key is set via file rather than environment. It
reports presence, not validity.

## `storageops doctor`

```bash
storageops doctor
storageops doctor --json
```

Prints a concise readiness report: package/PyPI version, Node, Pi, install mode,
skill count, `httpmon`, API key source, default provider/model, and common key
source conflicts. It does not call the model or object storage. When a newer Pi
is published on npm, the `Pi` line notes it with the upgrade command — StorageOps
never auto-upgrades an already-installed Pi.

`doctor` **exits non-zero when not ready** (not installed, no API key, or Pi/Node
below the minimum), so it can gate a script: `storageops doctor && storageops ...`.

`doctor --json` prints the same readiness as a machine-readable, **redacted**
object (it reports the API key *source*, never the key value) including `ready`
and `next_action`. Use it for support reports and automation instead of a
separate bundle command.

## `storageops configure`

```bash
storageops configure --provider deepseek --model deepseek-v4-pro
storageops configure --api-key
storageops configure --show
```

Writes local Pi settings under `~/.storageops/agent/` by default. `--api-key`
stores a model-provider key in `api-key` with `chmod 600`; if `--provider` is
also provided, the key is stored with a `provider:` prefix. Use `--merge` only
when intentionally configuring the existing `~/.pi/agent/` setup.

## `storageops smoke`

```bash
storageops smoke --provider deepseek --model deepseek-v4-pro
```

Runs one explicit `pi --print hello` model call to prove the configured model key
works. It never touches object storage and is not run by `install` or `doctor`.

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

A bare key in the `api-key` file is routed to the first unset of
`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`. To bind it to a
specific provider, prefix the value with `provider:` — e.g. `anthropic:sk-ant-...`
or `gemini:AIza...`. Recognized prefixes: `anthropic`/`claude`, `deepseek`,
`openai`, `google`/`gemini`, `mistral`, `groq`, `cerebras`. The `--version`
command's `api key` line reports which source is in effect.

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

## Diagnostic Tools

StorageOps registers a small Pi tool surface:

| Tool | Default posture |
| --- | --- |
| `scan_secrets` | Inline value-level redaction of credential-shaped text. |
| `detect_domain` | Inline routing hint with matched signals and recommended skill. |
| `search_memory` | Read-only search of scoped prior sessions with redacted snippets. |
| `capture_http_trace` | Bounded httpmon wrapper: known commands must be read-only; unknown commands run as bounded observation (still executed). |

The inline tools are intentionally small. `scan_secrets` returns line/column,
type, length, fingerprint, bounded redacted text, and no raw secret preview.
`detect_domain` returns ranked domains, matched signals, a recommended skill,
an ambiguity flag, and a best-effort storage **provider**
(aws/bos/oss/cos/gcs/azure/obs/minio) detected from the endpoint host, vendor
header prefixes, or CLI — with a pointer to that provider's quirks reference — so
provider-specific behavior is applied even when the user never names the
provider. The provider is a hint to verify, not a fact. `search_memory` tokenizes
the query, scores summary/JSONL matches, caps result count at 10, and redacts
returned snippets.

`capture_http_trace` is intentionally not a general httpmon interface. It
requires a `filter_host`, rejects shell commands, rejects mutating object-storage
operations, keeps `capture_body=false`, does not write HAR or record files, and
does not replay requests. Its output is a sanitized summary of method, host,
path template, status, signing shape, S3 error code, and **sanitized response
headers** (diagnostic metadata passes through; cookie/auth header values are
masked; redirect targets are stripped of presigned signatures).

The command validator checks the storage client's operation position rather
than treating every bucket, prefix, or key argument as an operation. This keeps
read-only metadata requests working even when object names contain words like
`delete`, `copy`, or `sync`. If a command URL host differs from `filter_host`,
the tool warns that the trace may capture zero requests instead of rejecting the
run.

The tool executes the wrapped command, so it is read-only by design: mutating
operations are rejected rather than traced. A rejected write trace returns a
`guidance` field pointing to the write-side evidence ladder (read the server
error body and the client's own debug dump, then recompute offline) so a failing
PUT/copy stays diagnosable without performing the write.

The safety tiers are:

- **Known read-only commands** (e.g. `aws s3api head-object`, `rclone ls`): allowed.
- **Known mutating/write or presigned material**: rejected.
- **Unknown commands** (custom SDK probes, vendor CLIs without a dedicated
  adapter): not rejected by executable name — they fall back to a stricter
  `unknown_observation` policy.

`unknown_observation` is capped at 5 requests and 15 seconds, requires the same
`filter_host`, rejects explicit HTTP write methods, warns on suspicious arguments
that may be operation names, and reports `method_violation=true` if captured
metadata shows a non-read-only HTTP method. **Because the wrapper executes the
command, an unknown command that itself mutates will perform that mutation** —
StorageOps can only prove a command is read-only when it recognizes it, so use
unknown-client observation only on commands you know are side-effect-free.
Known storage clients with unclassified, non-mutating commands also fall back to
bounded observation and return `operation_unclassified=true`.

`storageops install` automatically installs a verified `httpmon` helper into
`~/.storageops/bin/httpmon` when it is not already available. PyPI release
packages include the Linux amd64 helper used by common cloud VMs, so those
installs do not require users to preinstall httpmon, install Go, or download a
GitHub release at runtime. If the package lacks a matching bundled asset,
StorageOps falls back to a bounded network download and then to the normal
logs/debug path.
