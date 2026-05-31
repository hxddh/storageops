# StorageOps

StorageOps is an offline, read-only diagnostic toolkit for S3-compatible object storage operations. It combines deterministic parsers/analyzers in `storageops-core`, validated StorageOps skills in `agents/skills`, and a CLI for triage, analysis, report rendering, evaluation, audit, MCP, serve, and memory workflows.

## Agent Runtime: Pi Coding Agent

StorageOps Agent Runtime is **Pi Coding Agent**. StorageOps no longer owns an LLM provider layer, ReAct loop, model registry, provider headers, API key handling, base URL handling, streaming token loop, or native specialist-agent dispatcher. Configure providers, models, API keys, base URLs, and provider-specific settings in Pi Coding Agent.

`storageops-core` remains independent of Pi, LLM providers, model APIs, and real cloud credentials. It is the deterministic diagnostic engine for offline object storage evidence.

## Safety Model

- StorageOps remains offline and read-only.
- StorageOps never needs real object storage credentials for offline diagnosis.
- Do not provide real AK/SK, tokens, cookies, Authorization headers, or signed URLs.
- StorageOps redacts input before invoking Pi.
- Pi receives only a redacted temporary evidence file path and safe metadata.
- StorageOps validates Pi's report before printing it as final output.
- Mutating remediation commands must be labeled `manual-only`.

## Install

```bash
# Recommended: isolated install via pipx
pipx install git+https://github.com/hxddh/storageops.git#subdirectory=storageops-cli

# Or with pip
pip install git+https://github.com/hxddh/storageops.git#subdirectory=storageops-cli
```

## Setup (one-time)

Install Pi Coding Agent separately, then run:

```bash
storageops setup        # verifies Pi, installs skills to ~/.storageops/, writes config
storageops doctor       # verify everything is ready
```

`setup` writes:
- `~/.storageops/skills/` — StorageOps skill pack (copied from the installed package)
- `~/.storageops/.pi/settings.json` — Pi settings pointing to the installed skills
- `~/.storageops/config.json` — StorageOps config (Pi command, workdir, skills path)

After setup, `storageops diagnose` works from **any directory** — no repo clone needed.

## Pi Configuration

The repository includes `.pi/settings.json` configured to load StorageOps skills and enable skill commands. Paths in `.pi/settings.json` are relative to the `.pi` directory, so `../agents/skills` resolves to `agents/skills` at the repository root.

Configure providers and models in Pi, not StorageOps. You may pass Pi selection hints through the CLI:

```bash
storageops agent ./examples/rclone-etag-mismatch.log --pi-provider <provider> --pi-model <model>
```

## Run the Agent

```bash
storageops agent ./examples/rclone-etag-mismatch.log
storageops agent ./examples/s5cmd-429.log --stream
storageops agent ./evidence.log --runtime pi
```

Execution flow:

1. StorageOps reads the input file.
2. StorageOps redacts secrets and signed credentials.
3. StorageOps writes a temporary redacted evidence file.
4. StorageOps starts `pi --mode rpc`.
5. Pi loads StorageOps skills from `./agents/skills` and may call StorageOps CLI tools.
6. Pi returns a diagnostic report draft.
7. StorageOps validates YAML frontmatter, evidence sections, safety, and secret leakage.
8. StorageOps prints only the validated final report.

If Pi is missing, `storageops agent` fails with:

> Pi Coding Agent is required for storageops agent. Install and configure Pi first, or use non-agent commands such as storageops triage and storageops analyze.

## Agent Options

```text
storageops agent <file> [options]

  --runtime pi              Agent runtime; Pi is the only supported runtime
  --pi-command pi           Pi executable to run
  --pi-model <model>        Model hint passed through to Pi
  --pi-provider <provider>  Provider hint passed through to Pi
  --timeout-seconds 600     Pi RPC timeout
  --max-turns 8             Maximum Pi turns
  --stream                  Stream Pi event chunks
  --verbose                 Show runtime diagnostics
```

Removed StorageOps LLM flags such as `--llm-provider`, `--llm-model`, `--llm-base-url`, and `--llm-api-key` now fail with migration guidance:

> StorageOps no longer manages LLM providers. Configure providers and models in Pi Coding Agent.

## Non-Agent Commands (No Pi Required)

```bash
storageops triage <input-file>
storageops analyze <domain> <input-file>
storageops report <analysis-json>
storageops eval --all
storageops audit list
storageops serve
storageops mcp
storageops memory list
```

These commands continue to use offline parsers, analyzers, redaction, report rendering, safety validation, and golden case evaluation without Pi or LLM APIs.

## Skill Registry

`skill-registry.yaml` is retained as metadata, documentation, eval inventory, safety checklist, and consistency-check source. It is no longer the primary runtime router; Pi skill discovery from `./agents/skills` is the runtime mechanism.

Validate skill normalization with:

```bash
python scripts/check_skills.py
```

## Development Checks

```bash
python -m pytest
python scripts/check_skills.py
storageops --help
storageops agent --help
storageops triage --help
storageops analyze --help
storageops report --help
storageops eval --help
```
