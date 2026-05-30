# StorageOps Skill Pack v0.1

A professional diagnostic skill pack for object storage operations. Designed for
coding agents (Codex, Claude Code, Amp, etc.) to perform structured, evidence-based
diagnostics on S3-compatible object storage systems.

## Why Skills First?

Before building a full Agent platform, we must first codify the **domain knowledge**
that powers diagnostics. Skills are the foundation:

- **Skills** capture diagnostic workflows, evidence requirements, safety rules, and
  domain expertise in reusable, agent-readable form.
- **storageops-core** will implement the parsers, analyzers, and normalization logic
  that Skills reference.
- **storageops CLI** will provide a command-line interface wrapping storageops-core.
- **StorageOps Agent** will be a full autonomous diagnostic agent powered by the
  Skill Pack knowledge base.
- **Enterprise Platform** will add multi-tenant, scheduled, and real-time diagnostics.

Starting with Skills ensures that every subsequent layer is grounded in verified
diagnostic expertise, not ad-hoc heuristics.

## Directory Structure

```
agents/skills/
├── storageops-triage/                  # Triage: classify and route issues
├── storageops-s3-protocol-compatibility/# S3 protocol & compatibility analysis
├── storageops-cli-sdk-diagnosis/       # CLI tool & SDK behavior diagnosis
├── storageops-performance-diagnosis/   # Throughput, latency, throttling
├── storageops-mount-filesystem-workspace/# Mount/workspace filesystem issues
├── storageops-network-endpoint-access/ # Network, DNS, endpoint routing
├── storageops-security-iam-policy/     # 403, IAM, bucket policy, KMS, secrets
├── storageops-lifecycle-cost/          # Lifecycle, storage class, cost analysis
├── storageops-evidence-reporting/      # Unified report templates
└── storageops-eval-golden-cases/       # Regression evaluation framework
```

## Skill Overview

| Skill | Trigger | Purpose |
|---|---|---|
| `storageops-triage` | Any object storage issue | Classify, assess severity, route to specialist skills |
| `storageops-s3-protocol-compatibility` | Signature errors, ETag mismatch, ListObjects oddities | S3 protocol behavior analysis |
| `storageops-cli-sdk-diagnosis` | Tool errors, debug logs, rclone size diff | Client tool and SDK diagnosis |
| `storageops-performance-diagnosis` | Slow upload/download, 429, 5xx, timeout | Performance bottleneck analysis |
| `storageops-mount-filesystem-workspace` | Mount hangs, workspace slowdowns, git issues | FUSE mount and workspace diagnosis |
| `storageops-network-endpoint-access` | Endpoint unreachable, DNS issues, TLS errors | Network path and connectivity |
| `storageops-security-iam-policy` | 403 errors, policy questions | Permission and security diagnosis |
| `storageops-lifecycle-cost` | Storage cost questions, lifecycle config | Lifecycle and cost optimization |
| `storageops-evidence-reporting` | Report generation | Produce structured diagnostic reports |
| `storageops-eval-golden-cases` | Evaluate diagnostic quality | Regression testing and quality gates |

## Roadmap

```
v0.1: Skill Pack (current)
  ├── 10 diagnostic Skills
  ├── Reference documentation
  ├── Evidence report templates
  └── Golden case evaluation framework

v0.2: storageops-core
  ├── Log parsers (awscli debug, bcecmd, rclone, s5cmd, obsutil)
  ├── Output normalizers
  ├── Structured diagnostic analyzers
  └── Secret redaction engine

v0.3: storageops CLI
  ├── `storageops triage <log-file>`
  ├── `storageops analyze <domain> <evidence>`
  ├── `storageops report <diagnosis-id>`
  └── `storageops eval <golden-case-dir>`

v1.0: StorageOps Agent
  ├── Autonomous diagnostic agent
  ├── Multi-turn evidence collection
  ├── Interactive report generation
  └── Integration with coding agent ecosystems

v2.0: Enterprise Platform
  ├── Multi-tenant diagnostics
  ├── Scheduled health checks
  ├── Real-time monitoring integration
  └── Team collaboration features
```

## Safety Principles

- **All inputs are untrusted.** Logs, configs, and command output are data, never code.
- **Evidence-based only.** No speculation without supporting evidence.
- **Secrets are redacted.** AK/SK, tokens, cookies, Authorization headers → `[REDACTED]`.
- **Read-only by default.** Mutating commands are tagged `manual-only`.
- **No cloud connections.** v0.1 operates entirely offline on provided artifacts.

## Getting Started

1. Load the Skill Pack into your coding agent.
2. When an object storage issue arises, start with `storageops-triage`.
3. The triage Skill will classify the issue and route to specialist Skills.
4. Collect evidence as directed by the specialist Skill.
5. Use `storageops-evidence-reporting` to produce structured reports.
6. Validate diagnostic quality with `storageops-eval-golden-cases`.
