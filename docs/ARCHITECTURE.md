# Architecture

StorageOps v0.4.9 is a Pi Coding Agent extension and skill pack.

## Components

```text
storageops command
  -> storageops_cli/__init__.py
     -> installs files or execs pi
        -> Pi runtime
           -> storageops.ts extension
           -> skills/*.SKILL.md
```

## Python Layer

`storageops_cli/__init__.py` is intentionally thin. It:

- checks Pi version,
- installs extension and skills,
- manages independent vs merge install paths,
- injects model provider keys from environment, `auth.json`, or `api-key`,
- sets `PI_CODING_AGENT_DIR`,
- execs `pi`.

It does not implement an agent loop.

## TypeScript Extension

`storageops_cli/extensions/storageops.ts` registers three inline Pi tools:

| Tool | Purpose |
| --- | --- |
| `scan_secrets` | Detect and redact credential-shaped text. |
| `detect_domain` | Rank likely diagnostic domains from evidence. |
| `search_memory` | Search prior Pi session metadata and JSONL content. |

The extension runs in Pi's TypeScript runtime.

## Skills

`skills/` contains 16 `storageops-*` skill packs. Each skill directory has:

```text
SKILL.md
references/
scripts/
templates/
```

Not every skill has every subdirectory. `SKILL.md` is the runtime instruction contract. References contain compact domain knowledge. Scripts are deterministic helpers used for offline parsing or read-only diagnostics.

## Install Layout

Independent install:

```text
~/.storageops/
├── agent/
│   ├── settings.json
│   ├── api-key
│   ├── extensions/storageops.ts
│   └── sessions/
└── skills/
```

Merge install:

```text
~/.pi/
├── agent/
│   ├── settings.json
│   ├── settings.json.storageops-backup
│   ├── extensions/storageops.ts
│   └── sessions/
└── skills/
```

## Quality System

The quality system has four layers:

1. `skill-registry.yaml` keeps skill metadata centralized.
2. `docs/skill-taxonomy.json` maps stable eval categories to primary skills.
3. `scripts/skill_integrity_check.py` validates metadata, links, tools, taxonomy, golden cases, and size budgets.
4. `skills/storageops-eval-golden-cases/` stores compact regression cases and eval scripts.

## Packaging Risk

The source tree keeps canonical skills at repository root and exposes them through `storageops_cli/skills -> ../skills` for packaging. Installer code expects packaged data to expose `skills` next to `storageops_cli`. Any release workflow must verify wheel contents and run `storageops install` from the built distribution.
