# storageops-core v0.2

Parsers and analyzers for StorageOps diagnostic pipeline. All modules operate
on offline artifacts (log files, error responses, configurations). No network
calls, no cloud SDK calls, no real credentials.

## Modules

### Utils (shared)
- `secret_scanner.py` — Redact secrets before processing

### Parsers (raw → structured)
- `parse_awscli_debug.py` — awscli --debug output → structured trace
- `parse_rclone_log.py` — rclone -vv output → transfer records
- `parse_sigv4_error.py` — SignatureDoesNotMatch XML → canonical request diff
- `parse_s5cmd_log.py` — s5cmd --log debug → operation timing
- `parse_lifecycle_xml.py` — lifecycle XML → rule list

### Analyzers (structured → diagnosis)
- `analyze_throughput.py` — timing data → efficiency ratio, bottleneck
- `detect_throttling.py` — error log → throttle onset rate, affected scope
- `analyze_policy.py` — IAM/bucket policy JSON → denial source trace
- `analyze_metadata_amplification.py` — syscall profile → RTT × stat cost estimate
- `analyze_cost.py` — inventory data → per-prefix cost attribution
- `eval_runner.py` — golden case → pass/fail score

## Usage

All modules read from stdin or a file path argument and write JSON to stdout:

```bash
cat awscli-debug.log | python -m storageops-core.parsers.parse_awscli_debug > trace.json
python -m storageops-core.parsers.parse_awscli_debug awscli-debug.log > trace.json
```

## Output contract

Every module outputs JSON with at minimum:
```json
{
  "ok": true,
  "module": "parse_awscli_debug",
  "redacted": false,
  "...": "..."
}
```

On failure:
```json
{
  "ok": false,
  "module": "parse_awscli_debug",
  "error": "description",
  "...": null
}
```
