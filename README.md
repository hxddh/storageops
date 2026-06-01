# StorageOps

S3-compatible object storage diagnostic toolkit. A **Pi Coding Agent extension + skill pack** — StorageOps teaches AI agents to diagnose object storage issues across security, performance, network, lifecycle, replication, and more.

## What is StorageOps?

StorageOps is a set of **15 diagnostic skill packs** and **3 tools** that run as a Pi Coding Agent extension. It teaches the AI agent how to:

- 🔍 **Triage** storage issues by scanning logs, errors, and user reports
- 🛡️ **Detect and redact credentials** before analysis
- 📊 **Diagnose** root causes across 12+ domains (IAM, throttling, TLS, replication, cost...)
- 📝 **Generate** structured diagnosis reports with evidence and recommendations
- 🧪 **Validate** diagnosis quality with golden test cases

StorageOps is **not a standalone agent** — it runs on top of Pi Coding Agent, which handles the agent loop, session management, tool dispatch, and UI.

## Architecture

```
User → pi (Pi Coding Agent)
         │
         ├─ .pi/extensions/storageops.ts  ← 3 tools (scan_secrets, detect_domain, search_memory)
         │
         └─ skills/  ← 15 diagnostic skill packs
              ├─ storageops-triage/
              ├─ storageops-security-iam-policy/
              ├─ storageops-performance-diagnosis/
              ├─ storageops-network-endpoint-access/
              ├─ ... (11 more)
              └─ storageops-eval-golden-cases/
```

**Zero Python agent code.** The old 48-file Python agent package has been removed. StorageOps is now a pure Pi extension + skill pack.

## Install

```bash
# Install Pi Coding Agent
curl -fsSL https://raw.githubusercontent.com/hxddh/storageops/main/scripts/install-pi.sh | bash

# Clone StorageOps skill pack
git clone https://github.com/hxddh/storageops.git ~/.pi/storageops

# Configure Pi to use StorageOps
ln -sf ~/.pi/storageops/.pi/extensions/storageops.ts ~/.pi/agent/extensions/storageops.ts
ln -sf ~/.pi/storageops/skills ~/.pi/agent/skills/storageops

# Or use the thin CLI shim
cd ~/.pi/storageops && pip install -e .
```

Requires:
- **Pi Coding Agent** (>= v0.78.0) — `which pi`
- **Node.js** (>= 18) — for running Pi
- **Python** (>= 3.11) — optional, for the thin CLI shim

## Quick Start

```bash
# Start Pi with StorageOps skills loaded
pi --skills ~/.pi/storageops/skills

# Or use the thin CLI wrapper
storageops
```

Then just start talking:

```
> I have a 403 AccessDenied error in my S3 bucket. Here's my IAM policy: ...
> rclone sync is failing with "corrupted on transfer" for large files
> My s5cmd sync is getting 429 SlowDown errors
```

The AI agent automatically:
1. Runs `scan_secrets` to redact credentials
2. Runs `detect_domain` to classify the issue
3. Activates the relevant skill pack(s)
4. Diagnoses root cause and recommends fixes

## Skill Packs

| Skill | Domain |
|-------|--------|
| `storageops-triage` | Auto-classify issue domain from evidence |
| `storageops-security-iam-policy` | 403, AccessDenied, IAM, KMS, bucket policy |
| `storageops-performance-diagnosis` | 429, SlowDown, throughput, throttling |
| `storageops-network-endpoint-access` | DNS, TLS, VPC endpoint, connectivity |
| `storageops-cli-sdk-diagnosis` | awscli, boto3, rclone, s5cmd, bcecmd, obsutil |
| `storageops-lifecycle-cost` | Lifecycle rules, storage class, cost optimization |
| `storageops-replication-versioning` | CRR, SRR, versioning, replication lag |
| `storageops-migration-sync` | Cross-cloud migration, data sync |
| `storageops-mount-filesystem-workspace` | FUSE mount, rclone mount, s3fs |
| `storageops-data-consistency` | Stale reads, replica mismatch, ETag mismatch |
| `storageops-bigdata-pipeline` | Spark, Hive, Hadoop S3A connector |
| `storageops-event-notification` | S3 event notifications, SQS, Lambda |
| `storageops-s3-protocol-compatibility` | SigV4, CORS, ETag, API compatibility |
| `storageops-evidence-reporting` | Structured diagnosis report generation |
| `storageops-eval-golden-cases` | Golden-case regression testing |

## Tools

| Tool | Purpose |
|------|---------|
| `scan_secrets` | Scan and redact credentials (AWS keys, tokens, rclone secrets) |
| `detect_domain` | Classify evidence into diagnostic domains |
| `search_memory` | Search past sessions for similar issues |

## CLI Commands

The thin CLI shim forwards to Pi:

```bash
storageops                    # Interactive REPL (same as `pi`)
storageops "diagnose 403..."  # Single-turn diagnosis
```

All diagnostic work happens through Pi's agent loop. There are no separate CLI subcommands for each diagnosis type — just describe the problem naturally.

## Supported Providers

- AWS S3
- Alibaba Cloud OSS
- Tencent Cloud COS
- Baidu BOS
- MinIO
- Ceph RGW
- GCP Cloud Storage (S3-compatible)
- Any S3-compatible endpoint

## Development

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops

# Edit the extension
vim .pi/extensions/storageops.ts

# Edit skill packs
vim skills/storageops-triage/SKILL.md

# Test with Pi
pi --skills ./skills
```

### Project Structure

```
storageops/
├── .pi/
│   ├── extensions/storageops.ts   ← Pi extension (3 tools)
│   └── settings.json
├── skills/                        ← 15 diagnostic skill packs
│   ├── storageops-triage/
│   ├── storageops-security-iam-policy/
│   └── ...
├── docs/                          ← Documentation
├── scripts/                       ← Utility scripts
├── AGENTS.md                      ← Agent instruction file
├── README.md
├── CONTRIBUTING.md
├── pyproject.toml                 ← Thin CLI shim build
└── storageops_cli.py              ← Pi forwarding shim
```

## Security

StorageOps never connects to real cloud accounts, executes write operations, or exposes credentials. The `scan_secrets` tool redacts all credentials before any analysis. See [SECURITY.md](SECURITY.md) for details.

## License

MIT
