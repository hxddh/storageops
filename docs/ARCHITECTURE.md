# Architecture

StorageOps v0.4.51 is a Pi Coding Agent extension and skill pack.

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

`storageops_cli/extensions/storageops.ts` registers four Pi tools:

| Tool | Purpose |
| --- | --- |
| `scan_secrets` | Detect credential-shaped text, redact sensitive values, and return safe fingerprints. |
| `detect_domain` | Rank likely diagnostic domains, matched signals, and the recommended skill. |
| `search_memory` | Search prior Pi session metadata/JSONL with scored, redacted snippets. |
| `capture_http_trace` | Run one bounded read-only command through httpmon and return a sanitized HTTP summary. |

The first three tools run fully inline in Pi's TypeScript runtime. They are
bounded and credential-averse: secret scanning caps large inputs, memory search
redacts returned snippets, and domain detection returns routing hints rather
than executing any workflow.
`capture_http_trace` may invoke the external `httpmon` binary, but only through
a narrow wrapper: no shell, no mutating commands, no body capture, no HAR/record
files, and no replay. Its validator keeps hard rejections small: explicit write
methods, clear mutating operation positions, presigned material, and unsafe
execution wrappers are blocked. Unclassified clients or operations fall back to
bounded metadata observation with smaller request/time caps instead of being
rejected merely because StorageOps lacks a dedicated adapter. Host mismatch is
surfaced as a warning rather than a hard rejection, because endpoint aliases and
redirects are common in object-storage diagnosis.

The tool *executes* the wrapped command, so it only guarantees no side effects
for commands it can prove read-only; that is why mutating operations are not
traced. Write-side failures (a failing PUT/copy, e.g. `BadDigest` or
`SignatureDoesNotMatch`) are diagnosed from the request's evidence — the server
error body, the client's own debug dump, and offline recompute — never by
re-issuing the write. A rejected write trace returns `guidance` pointing at that
evidence ladder. Read-only trace use is unchanged.

`storageops install` automatically prepares a verified `httpmon` helper in
`~/.storageops/bin/httpmon`. Release wheels carry the gzip-compressed Linux
amd64 helper used by common cloud VMs; other supported platforms and source
checkouts can still fall back to a bounded download. The extension also looks in
the managed location, so merged Pi installs do not need users to edit `PATH`.

## Skills

`skills/` contains 15 diagnostic `storageops-*` skill packs plus 1 eval skill pack. Each skill directory has:

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
