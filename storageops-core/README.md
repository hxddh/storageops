# storageops-core

Parsers and analyzers for StorageOps diagnostic pipeline. All modules operate on offline
artifacts (log files, error responses, configurations). No network calls, no cloud SDK
calls, no real credentials required.

## Modules

### Utils (shared)

- `secret_scanner.py` — Redact AK/SK, tokens, Authorization headers before processing
- `signatures.py` — Domain pattern matching (`auto_detect()`) — single source of truth

### Parsers (raw text → structured dict)

| Parser | Input |
|--------|-------|
| `parse_awscli_debug.py` | `aws --debug` output |
| `parse_rclone_log.py` | `rclone -vv` output |
| `parse_sigv4_error.py` | `SignatureDoesNotMatch` XML error response |
| `parse_s5cmd_log.py` | `s5cmd --log debug` output |
| `parse_lifecycle_xml.py` | S3 lifecycle configuration XML |
| `parse_cors_error.py` | CORS error messages and preflight headers |
| `parse_network_diagnostics.py` | `dig`/`curl -v`/`ping`/`traceroute` output |
| `parse_replication_status.py` | Replication metadata and status JSON |
| `parse_hadoop_s3a.py` | Hadoop/Spark S3A error logs |
| `parse_httpmon_log.py` | httpmon NDJSON (`--format json`) or HAR (`--har`) output |

### Analyzers (structured dict → diagnosis)

| Analyzer | What it produces |
|----------|-----------------|
| `analyze_throughput.py` | Efficiency ratio, bottleneck layer, tuning recommendations |
| `detect_throttling.py` | Throttle onset rate, affected prefix scope, 429/SlowDown patterns |
| `analyze_policy.py` | IAM / bucket policy denial source trace |
| `analyze_network.py` | DNS/TLS/TCP/VPC endpoint root cause from parsed diagnostics |
| `analyze_cors.py` | CORS misconfiguration root cause and fix |
| `analyze_replication.py` | CRR/SRR failure classification |
| `analyze_metadata_amplification.py` | RTT × stat cost estimate for FUSE mounts |
| `analyze_cost.py` | Per-prefix cost attribution from inventory data |
| `eval_runner.py` | Golden case → pass/fail score |

## Output contract

Every module returns a dict with at minimum:

```json
{
  "ok": true,
  "module": "parse_awscli_debug"
}
```

On failure:

```json
{
  "ok": false,
  "module": "parse_awscli_debug",
  "error": "description"
}
```

## Design rules

- **Zero runtime dependencies** — no `pip install` required; runs anywhere Python ≥ 3.10 is available.
- **Flat imports** — `from parse_rclone_log import parse`, not `from storageops_core.parsers...`.
  The CLI bridges this with a `sys.path` injection.
- **No imports from `storageops-cli`** — dependency only flows one way.
- **Secrets never reach analyzers** — `secret_scanner.scan()` must be called before any parser.

## Adding a parser

1. Create `parsers/parse_<name>.py` with `parse(text: str) -> dict`.
2. Add a test in `tests/test_parsers.py`.
3. Register as a tool in `storageops-cli/storageops/tool_registry.py`.
4. Add a minimal-input entry to `storageops-cli/tests/test_mcp_server.py::TestToolRegistryConsistency`.
