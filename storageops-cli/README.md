# StorageOps CLI v0.3

Command-line interface wrapping storageops-core parsers and analyzers.

## Quick Start

```bash
# Without pip install (development):
cd StorageOps/
PYTHONPATH="storageops-cli:$PYTHONPATH" python3 -m storageops.cli <command>

# Or use the wrapper:
./storageops-cli/storageops.sh <command>
```

## Commands

### `triage` — Classify evidence

```bash
storageops triage <evidence-file>
```

Auto-detects issue domain, input type, and routes to the correct specialist skill.
Runs secret scan before analysis.

**Output:** JSON with `primary_domain`, `confidence`, `routing.primary_skill`, `recommended_next_command`.

### `analyze` — Run domain-specific analysis

```bash
storageops analyze <domain> <evidence-file> [--subdomain <sub>] [--no-redact]
```

Runs parser + analyzer pipeline for a specific domain. Available domains:

| Domain | What it analyzes |
|---|---|
| `s3_protocol_compatibility` | SigV4 errors, XML error responses |
| `cli_sdk_behavior` | rclone, awscli, s5cmd debug logs |
| `performance_throughput` | Timing data, throttling patterns |
| `mount_filesystem_workspace` | Metadata amplification (JSON input) |
| `network_endpoint_access` | Network guidance (manual tools needed) |
| `security_iam_policy` | IAM/bucket policy JSON |
| `lifecycle_cost` | Inventory cost data JSON |

**Output:** Structured JSON with diagnosis, root cause, recommendations.

### `report` — Generate markdown report

```bash
storageops report <analysis-json>
```

Converts analysis JSON to a structured markdown report.

### `eval` — Run golden case evaluation

```bash
storageops eval --case <case-name>
storageops eval --all
```

Evaluates diagnostic output against golden case expectations.

## Full Pipeline Example

```bash
# 1. Triage the evidence
storageops triage rclone-debug.log > triage.json

# 2. Read triage output, then run analysis
storageops analyze cli_sdk_behavior rclone-debug.log > analysis.json

# 3. Generate report
storageops report analysis.json > diagnosis-report.md

# 4. Evaluate quality
storageops eval --case rclone-corrupted-transfer
```

## Installing (pip)

```bash
pip install -e storageops-cli/
```

Then use `storageops` as a global command.
