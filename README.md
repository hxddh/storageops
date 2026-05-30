# StorageOps v1.0

[![CI](https://github.com/YOUR_USERNAME/storageops/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/storageops/actions)

A professional diagnostic system for object storage operations. Stack:
- **Skills** — 10 agent-readable diagnostic skills with reference docs
- **Core** — 5 parsers + 5 analyzers + secret scanner (offline, no cloud deps)
- **CLI** — `storageops triage|analyze|report|eval|agent`
- **Agent** — autonomous multi-turn evidence collection and diagnosis

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/storageops.git
cd storageops
pip install -e storageops-cli/

# Run the agent on a debug log
storageops agent agents/skills/storageops-eval-golden-cases/cases/rclone-corrupted-transfer/input/rclone-debug.log
```

## Architecture

```
agents/skills/          ← v0.1: 10 diagnostic Skills (knowledge layer)
    ↓ references
storageops-core/         ← v0.2: Parsers + Analyzers (processing layer)
    ↓ imports
storageops-cli/          ← v0.3: CLI (interface layer)
    └── storageops agent ← v1.0: Autonomous Agent (orchestration layer)
```

Each layer builds on the one below. Skills define what to diagnose, Core
parses raw data, CLI wraps it as commands, Agent orchestrates multi-turn
conversations.

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
v0.1: Skill Pack ✅
  ├── 10 diagnostic Skills
  ├── Reference documentation
  ├── Evidence report templates
  └── Golden case evaluation framework

v0.2: storageops-core ✅
  ├── 5 parsers (awscli, rclone, s5cmd, sigv4, lifecycle XML)
  ├── 5 analyzers (throughput, throttling, policy, metadata amp, cost)
  ├── Secret scanner (11 patterns)
  └── Eval runner (7-dimension scoring + unsafe output gates)

v0.3: storageops CLI ✅
  ├── `storageops triage <evidence>`
  ├── `storageops analyze <domain> <input>`
  ├── `storageops report <analysis.json>`
  └── `storageops eval --all`

v1.0: StorageOps Agent ✅
  ├── Autonomous multi-turn evidence collection
  ├── Multi-domain detection and routing
  ├── Evidence quality assessment
  └── Structured diagnostic report generation

v2.0: Enterprise Platform (future)
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
- **No cloud connections.** Operates entirely offline on provided artifacts.

## Testing

```bash
# Smoke tests (7 parsers + analyzers)
python storageops-core/tests/smoke_test.py

# Real-world validation (5 cases)
python tests/validation/run_validation.py

# Golden case evaluation
storageops eval --cases-dir agents/skills/storageops-eval-golden-cases/cases \
  --outputs-dir docs/examples --case rclone-corrupted-transfer
```
