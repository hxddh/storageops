# StorageOps

StorageOps is a Pi Coding Agent extension and skill pack for diagnosing S3-compatible object storage problems.

It is designed for cases like `AccessDenied`, `SlowDown`, `SignatureDoesNotMatch`, checksum mismatches, stale reads, broken lifecycle rules, failed notifications, and migration surprises. You provide logs, errors, configs, or a short description; Pi loads the StorageOps skills and tools to produce an evidence-based diagnosis.

## What You Get

- 16 diagnostic skills covering security, protocol compatibility, CLI/SDK behavior, performance, network access, lifecycle cost, replication, mount/workspace usage, migration, data consistency, access logs, big-data pipelines, notifications, reporting, and triage, plus 1 eval skill pack.
- 3 Pi extension tools:
  - `scan_secrets` redacts credentials and tokens.
  - `detect_domain` ranks likely diagnostic domains from evidence text.
  - `search_memory` searches prior Pi sessions for related diagnoses.
- Deterministic helper scripts for access logs, policy analysis, throttling, ETags, small-object cost, migration estimates, SigV4 parsing, endpoint reachability, and golden-case eval.
- A regression suite with 33 compact golden cases and size gates to keep the repository lean.

## Quick Start

**Prerequisites:** Node.js 18+, Python 3.11+, and a model provider key.

```bash
# 1. Install Pi Coding Agent (the runtime engine)
#    storageops install does this automatically, but you can also install manually:
npm install -g @earendil-works/pi-coding-agent

# 2. Install StorageOps
python3 -m pip install storageops
storageops install

# 3. Configure a model key (pick one)
export ANTHROPIC_API_KEY=sk-...
export DEEPSEEK_API_KEY=sk-...
export OPENAI_API_KEY=sk-...

# 4. Run a diagnosis
storageops --print 's5cmd sync reports 429 SlowDown; diagnose likely cause'
```

> **Ubuntu / Debian:** If `pip install storageops` fails with
> "externally-managed-environment", use
> `python3 -m pip install storageops --break-system-packages` or create a
> virtualenv first.
>
> **Cloud or regional PyPI mirrors:** If your default mirror reports
> "No matching distribution found for storageops", install from the official
> PyPI index:
>
> ```bash
> python3 -m pip install --upgrade storageops -i https://pypi.org/simple
> ```

`storageops install` automatically installs Pi Coding Agent via npm if it is not
already present. It stops before deployment when an older Pi version is detected
and prints the manual upgrade command, avoiding both auto-upgrades and half-ready
StorageOps installs.

## Configure a Model Key

Use any one of these patterns:

```bash
export DEEPSEEK_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
```

Or store a local key for the selected StorageOps/Pi agent directory:

```bash
echo sk-... > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
```

You can also pass Pi-native options through `storageops`, for example `--provider`, `--model`, `--api-key`, `--print`, `--resume`, or `@file` inputs.

DeepSeek smoke test:

```bash
storageops --provider deepseek --model deepseek-v4-pro --print 'hello'
```

`deepseek-v4-pro` and `deepseek-v4-flash` are known-good DeepSeek choices with
Pi 0.78.0. If you keep a key in `~/.storageops/agent/api-key`, StorageOps reads
it and exposes it to Pi; you do not need to pass `--api-key` for normal use.

## Install Modes

Independent mode is the default:

```bash
storageops install
```

It writes:

```text
~/.storageops/
├── agent/
│   ├── settings.json
│   ├── api-key
│   ├── extensions/storageops.ts
│   └── sessions/
└── skills/
```

Merge mode installs into an existing Pi setup:

```bash
storageops install --merge
```

It writes the extension to `~/.pi/agent/extensions/`, skills to `~/.pi/skills/`, and backs up `settings.json` before merging StorageOps settings.

## Typical Workflows

Single-shot diagnosis:

```bash
storageops --print @rclone-debug.log 'Explain the checksum mismatch and safe next steps'
```

Interactive diagnosis:

```bash
storageops
```

Refresh an install after upgrade:

```bash
python3 -m pip install --upgrade storageops
storageops install --force
```

Run quality gates from a checkout:

```bash
python3 scripts/skill_integrity_check.py
python3 skills/storageops-eval-golden-cases/scripts/golden_case_validator.py \
  skills/storageops-eval-golden-cases/cases
make validate
```

## Documentation Map

- [Getting Started](docs/getting-started.md)
- [CLI Reference](docs/cli-reference.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Quick Reference](docs/quick-reference.md)
- [Release](docs/release.md)
- [Tutorial](docs/tutorial.md)
- [Skill Quality Guide](docs/skill-quality-guide.md)
- [Skill Taxonomy](docs/skill-taxonomy.md)
- [Routing Flowchart](docs/skill-routing-flowchart.md)
- [Dependency Map](docs/skill-dependency-map.md)
- [API Coverage Matrix](docs/api-coverage-matrix.md)
- [Examples](docs/examples/)
- [Changelog](CHANGELOG.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## Repository Note

The source tree keeps canonical skills at repository root and exposes them through `storageops_cli/skills -> ../skills` for packaging. The installer expects packaged skills to be available next to `storageops_cli`; review distribution changes carefully.

## License

MIT
