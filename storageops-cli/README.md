# StorageOps CLI

The StorageOps CLI wraps deterministic `storageops-core` parsers/analyzers and the Pi Coding Agent runtime.

## Agent Runtime

`storageops agent <file>` uses **Pi Coding Agent** by default. StorageOps does not manage LLM providers, API keys, base URLs, provider headers, model registries, or native ReAct loops. Configure providers and models in Pi.

```bash
storageops agent ./examples/rclone-etag-mismatch.log
storageops agent ./examples/s5cmd-429.log --stream
storageops agent ./evidence.log --runtime pi --pi-command pi
```

If Pi is missing, the command reports that Pi Coding Agent is required and recommends using non-agent commands such as `storageops triage` and `storageops analyze`.

## Agent Options

```text
--runtime pi
--pi-command pi
--pi-model <model>
--pi-provider <provider>
--timeout-seconds 600
--max-turns 8
--stream
--verbose
```

Old `--llm-*` flags fail with: `StorageOps no longer manages LLM providers. Configure providers and models in Pi Coding Agent.`

## Non-Agent Commands (No Pi Required)

### `triage`

```bash
storageops triage <evidence-file>
```

Classifies evidence, assesses confidence, runs secret scanning, and suggests the next offline command.

### `analyze`

```bash
storageops analyze <domain> <evidence-file> [--subdomain <sub>] [--no-redact]
```

Runs domain-specific offline parser/analyzer logic. `storageops-core` remains independent of Pi and LLM providers.

### `report`

```bash
storageops report <analysis-json>
```

Renders an analysis JSON file as Markdown.

### `eval`

```bash
storageops eval --case <case-name>
storageops eval --all
```

Runs golden case evaluation without calling real LLM APIs.

## Safety

StorageOps remains offline and read-only. It never needs real object storage credentials for offline diagnosis, redacts evidence before Pi, and validates Pi output before printing a final report. Mutating remediation commands must be labeled `manual-only`.
