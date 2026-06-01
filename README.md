# StorageOps

> S3-compatible object storage diagnostic agent — powered by Pi Coding Agent.

StorageOps is a **natural-conversation diagnostic agent** for S3-compatible object storage systems.
Describe an error or paste a log, and StorageOps will parse, analyze, and diagnose the root cause —
with structured evidence, confidence scoring, and actionable remediation.

Zero cloud connections. Zero destructive actions. Built for production incident response.

## Supported Providers

AWS S3 · Alibaba Cloud OSS · Tencent Cloud COS · Baidu BOS · Huawei OBS · MinIO

## Install

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
pip install -e .
```

Requires Python ≥ 3.11.

### Pi Coding Agent

StorageOps uses Pi Coding Agent as its LLM engine for conversational diagnosis.
Pi is auto-installed via `storageops setup` (or `python -m storageops.pi_installer`).

```bash
storageops setup       # Install Pi + configure provider
```

## Quick Start

```bash
storageops             # Enter interactive REPL
```

Paste an error log and StorageOps will diagnose it. Conversation history is saved
automatically and resumed across sessions.

## REPL

| Command | Description |
|---------|-------------|
| `/exit` | Quit |
| `/resume` | Resume a previous session (picker UI) |
| `/history` | Show session conversation history |
| `/clear` | Start a new session |
| `/session` | Show current session info |
| `/search <query>` | Search past sessions |
| `/fork` | Fork current session into a new one |
| `$ command` | Run shell command |
| `@file` | Resolve file path for attaching |

## CLI Commands

| Command | Description |
|---------|-------------|
| `storageops` | Interactive REPL (default) |
| `storageops triage <log>` | Classify evidence domain |
| `storageops analyze <log>` | Run domain-specific analysis |
| `storageops diagnose <log>` | Full LLM-powered diagnosis |
| `storageops eval --all` | Run golden case evaluation |
| `storageops config` | Show configuration |
| `storageops setup` | Install Pi + configure provider |
| `storageops doctor` | Run system health checks |
| `storageops serve` | Start REST API server (port 8080) |
| `storageops audit` | View audit trail |
| `storageops resume [id]` | Resume a session |

## API Server

```bash
storageops serve --host 127.0.0.1 --port 8080
```

Endpoints:
- `GET /health` — Liveness check
- `POST /triage` — Classify evidence domain
- `POST /analyze` — Run domain-specific analysis
- `GET /domains` — List supported domains
- `GET /memory` — List recent sessions
- `GET /memory/search?q=...` — Search past diagnoses

## Architecture

```
User → REPL → Agent (converse) → Pi (LLM engine) → Tools (parser/analyzer)
                ↕                                ↕
           Session (JSONL) ← append events ← events stream

Session = append-only JSONL event log + meta.json sidecar.
Agent = stateless conversation loop. Pi = subprocess RPC bridge.
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

## Skills

14 specialized skill packs in `agents/skills/`:

| Skill | Domain |
|-------|--------|
| `storageops-triage` | Evidence classification |
| `storageops-cli-sdk-diagnosis` | SDK/CLI errors (rclone, s5cmd, awscli) |
| `storageops-s3-protocol-compatibility` | SigV4, clock skew, region mismatch |
| `storageops-security-iam-policy` | IAM/bucket policy analysis |
| `storageops-performance-diagnosis` | Throughput, throttling, small files |
| `storageops-lifecycle-cost` | Lifecycle rules, storage class, cost |
| `storageops-network-endpoint-access` | DNS, TLS, VPC endpoints |
| `storageops-bigdata-pipeline` | Hadoop/Spark S3A committer errors |
| `storageops-replication-versioning` | CRR/SRR replication failures |
| `storageops-mount-filesystem-workspace` | POSIX mount behavior |
| `storageops-evidence-reporting` | Structured report generation |
| `storageops-eval-golden-cases` | Golden case test suite |
| `storageops-data-consistency` | ETag/checksum/corruption |
| `storageops-event-notification` | S3 event notifications |
| `storageops-migration-sync` | Cross-provider migration |

## Security

- **Offline only** — never connects to cloud APIs
- **Read-only** — all mutating commands labeled `# manual-only:`
- **Secret-safe** — auto-redacts credentials before they reach LLM
- **No destruction** — never recommends deleting data, disabling encryption, or making buckets public

See [SECURITY.md](SECURITY.md).

## License

MIT
