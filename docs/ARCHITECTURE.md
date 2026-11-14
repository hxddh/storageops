# Architecture

StorageOps v2.0.0 is a Pi Coding Agent extension, skill pack, and read-only
evidence toolkit.

## Components

```text
storageops command
  -> storageops_cli/__init__.py       launcher + installer (no agent loop)
     -> installs the extension package and skills, then execs pi with:
        --no-builtin-tools --tools +read,+grep,+find,+ls
        -> Pi 1.x runtime
           -> extensions/storageops/index.ts  (9 tools + 4 hooks)
           -> skills/*/SKILL.md               (16 packs)
           -> contract/root-causes.json       (shared vocabulary)
```

## Python Layer

`storageops_cli/__init__.py` is intentionally thin. It checks the Pi version,
installs the extension directory and skills, prepares the `httpmon` helper,
manages independent vs merge installs, injects model keys from the environment,
`auth.json`, or `api-key`, and execs `pi` with the diagnosis tool policy. It does
not implement an agent loop and never talks to object storage itself.

## Extension

`storageops_cli/extensions/storageops/` is one multi-file extension. Pi treats
every top-level `*.ts` under `extensions/` as its own entry point, so the modules
live in a subdirectory with `index.ts`; shipping them flat made Pi reject the
extension and refuse to start (v0.8.0).

| Module | Responsibility |
| --- | --- |
| `index.ts` | Tool registration, runtime guards, persona. |
| `probe.ts` | Endpoint / bucket / capability probes; XML → facts. |
| `sigv4.ts` | SigV4 signing and credential resolution (env or `~/.aws/credentials`). |
| `diagnosis.ts` | Diagnosis schema, validation, canonical rendering. |
| `evidence.ts` | Session evidence registry (`ev_N` ids). |
| `cases.ts` | Redacted case store and search. |
| `trace.ts` | Bounded httpmon wrapper (HTTP/2, trailers, timing). |
| `secrets.ts` | Credential redaction. |
| `routing.ts` | Domain and provider hints. |
| `memory.ts` | Legacy transcript search (system entries are skipped). |
| `contract.generated.ts` | Generated from `contract/root-causes.json`; do not edit. |

### Tools

| Tool | Effect |
| --- | --- |
| `probe_endpoint` | DNS, TCP, TLS, HTTP HEAD, latency, clock skew. |
| `probe_bucket` | Signed GET/HEAD of bucket configuration → structured facts. |
| `probe_capabilities` | Classifies each S3 API as ok / denied / not configured / unsupported. |
| `run_analyzer` | Runs one allowlisted Python analyzer, argv only. |
| `capture_http_trace` | One bounded read-only command through httpmon. |
| `detect_domain`, `scan_secrets`, `search_cases` | Routing, redaction, case recall. |
| `submit_diagnosis` | Validates and renders the final diagnosis; records a case. |

Every probe is GET/HEAD. `probe_bucket` signs with credentials read from the
environment or the standard shared credentials file and returns only a redacted
identity label. Nothing in the extension declares a write operation.

### Runtime guards

- `input`: credential-shaped values are redacted before the model sees them.
- `tool_result`: redaction for `read`, `grep`, probes, analyzers, and traces.
- `tool_call`: blocks `bash`/`edit`/`write` and reads of credential stores when
  `STORAGEOPS_ENFORCE_READONLY=1` (the launcher sets it).
- `before_agent_start`: adds the StorageOps persona and evidence-first rule when
  `STORAGEOPS_MODE=diagnose`.

## Diagnosis Contract

`contract/root-causes.json` is the single source of truth: 15 domains, 106
root-cause ids, each with aliases for older vocabulary. Skills emit its ids; the
eval resolves legacy case terms through the same aliases; `submit_diagnosis`
rejects ids outside the route's domain; `scripts/gen_contract.py` generates the
extension table and `scripts/root_cause_contract_check.py` fails CI when the four
copies drift.

`submit_diagnosis` also rejects uncited claims (evidence ids must exist in the
session), missing falsifiers, and any remediation with `apply_by=agent`.

## Triage Is Advisory

`detect_domain` remains a deterministic hint (signals, provider, allowed root
causes). The model routes by skill descriptions and is checked by the eval; the
regex is no longer the only router.

## Quality System

1. `contract/` — one vocabulary for skills, eval, and runtime.
2. `docs/skill-taxonomy.json` — stable eval categories → primary skills.
3. `scripts/*_check.py` — contract, output-contract, provider scope, references,
   version, size, routing gates.
4. `skills/storageops-eval-golden-cases/` — 50 cases, 49 baselines, scored
   through the contract resolver.
5. `scripts/e2e_mock_test.sh` — packaged wheel → install → Pi 1.5.2 with a mock
   provider: extension loads, tool surface is read-only, a cited diagnosis is
   accepted, a case is recorded.

## Install Layout

```text
~/.storageops/
├── agent/
│   ├── settings.json
│   ├── api-key
│   ├── extensions/storageops/{index.ts,probe.ts,...}
│   └── sessions/
├── skills/                 (16 packs)
├── cases/                  (recorded diagnoses, 0600)
├── bin/httpmon             (v1.4.1)
└── install.json
```

## Packaging Risk

The source tree keeps canonical skills at repository root and exposes them to
packaging through `storageops_cli/skills -> ../skills`; the root-cause contract
is exposed the same way (`storageops_cli/contract -> ../contract`). Any
distribution change must rebuild the wheel and run `scripts/package_check.py`,
which now also fails on loose modules in `extensions/` and on a missing contract.
