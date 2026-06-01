# storageops-cli-sdk-diagnosis Scripts

Future scripts for this domain (not yet implemented in v0.1):

## Planned Scripts

### `parse_awscli_debug.py`
Parse awscli `--debug` output and extract:
- Request/response cycle timeline
- Credential resolution trace (redacted)
- CanonicalRequest and StringToSign
- Retry events with backoff timing
- Error codes and request IDs

### `the diagnostics tools`
Parse rclone `-vv --dump headers` output and extract:
- Transfer list with status (OK, FAILED, CORRUPTED)
- Checksum comparisons (source vs dest)
- Retry events
- Configuration dump (redacted)

### `parse_s5cmd_log.py`
Parse s5cmd `--log debug` output and extract:
- Operation timing per file
- Concurrency utilization
- Error distribution by status code
- Throttling events (429/SlowDown)

### `cross_tool_compare.py`
Given debug logs from two different tools against the same endpoint:
- Compare request formats (headers, URL style)
- Compare multipart thresholds and part sizes
- Identify configuration differences
- Report which tool is better configured for this endpoint

## Principles

- All scripts must operate on offline log files only.
- Debug logs may contain full request/response bodies — scan and redact secrets before processing.
- No network calls to real cloud endpoints.
- Output must be structured for downstream analysis.
