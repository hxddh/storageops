# CLI Reference

StorageOps v0.4.0 is a Pi Coding Agent extension + skill pack. All interaction is natural-language conversation through Pi's REPL or API.

## Usage

```bash
# Interactive REPL (with StorageOps skills loaded)
storageops

# Equivalent Pi invocation
pi --skills ~/.pi/storageops/skills

# Single-turn diagnosis
pi --skills ~/.pi/storageops/skills "s5cmd 429 SlowDown 报错"

# Resume a previous session
pi --resume <session-id>
```

## Slash Commands (in REPL)

| Command | Description |
|---------|-------------|
| `/editor` | Open $EDITOR for multi-line prompt input |
| `/view` | Open last assistant response in pager |
| `/history` | Show command history |
| `/exit` | Exit REPL |
| `/reload` | Reload extensions and skills |

## Prompt-Line Tips

| Input | Effect |
|-------|--------|
| `$ <command>` | Run shell command; output added to session evidence |
| `@<filename>` | Resolve file path; file content read into prompt |
| `\` at line end | Continue input on next line |
| `Tab` | File path completion (after @) |

## Environment

StorageOps uses Pi's native configuration. Configure provider and API key in Pi:

```bash
pi --provider deepseek --api-key sk-...
```

Or set environment variables:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export DEEPSEEK_API_KEY=sk-...
```

## Skills

15 skill packs in `skills/`. Pi auto-loads them via `--skills` flag. Each skill has trigger keywords that auto-activate when the conversation matches a specific domain.

To add a new domain, create a new directory under `skills/` with a `SKILL.md` file. No code changes required.

## Health Check

```bash
# Pi doctor check
pi doctor
```

## API Server

StorageOps does not include a standalone API server (removed in v0.4.0). Pi Coding Agent provides APIs through its SDK. See [Pi SDK documentation](https://github.com/earendil-works/pi/blob/main/docs/sdk.md).

## Previous Commands (removed in v0.4.0)

The following standalone CLI commands were removed when StorageOps was redesigned as a Pi extension:

- `storageops diagnose` — replaced by natural conversation in Pi REPL
- `storageops triage` — replaced by `detect_domain` tool
- `storageops analyze` — replaced by skill-pack instructions
- `storageops serve` — removed; use Pi SDK
- `storageops mcp` — removed; use Pi SDK
- `storageops config` — use Pi configuration
- `storageops setup` — use Pi setup + git clone
- `storageops doctor` — use `pi doctor`
- `storageops eval` — use golden cases manually
- `storageops audit` — use Pi session replay
- `storageops memory` — use Pi session list
- `storageops resume` — use `pi --resume`
