# MinIO Client (mc) Diagnosis

## Overview

`mc` (MinIO Client) is a modern, concurrent S3-compatible CLI written in Go.
It is compatible with AWS S3, MinIO, GCS, Azure Blob, and other S3-compatible
endpoints. Common issues: alias configuration errors, SSL certificate problems,
multipart upload failures, and concurrency-induced throttling.

---

## Configuration (Aliases)

mc uses named aliases instead of a config file:

```bash
# Add an alias (manual-only: redact credentials before sharing)
mc alias set myalias https://s3.amazonaws.com AKIAIOSFODNN7EXAMPLE wJalrXUtnFEMI --api s3v4

# List configured aliases
mc alias list

# Check a specific alias
mc alias list myalias
```

Stored in `~/.mc/config.json`. Redact `accessKey`/`secretKey` before sharing.

**`--api` parameter:**
- `s3v4` — SigV4 (required for AWS and most providers)
- `s3v2` — Legacy SigV2 (only for very old providers)
- If omitted, `mc` auto-detects

---

## Common Errors and Root Causes

### `mc: <ERROR> Unable to initialize new alias from the provided credentials. Access denied.`

**Cause options:**
1. Wrong credentials for the endpoint
2. Clock skew > 15 minutes
3. Wrong `--api` version (try `--api s3v4` explicitly)
4. The endpoint does not accept the S3 API at this URL

**Diagnosis:**
```bash
mc alias set test-alias https://s3.amazonaws.com AK SK --api s3v4
mc ls test-alias 2>&1
```

### `mc: <ERROR> Unable to validate SSL certificate`

**Cause:** Custom endpoint with self-signed or internal CA certificate.

**Do NOT** use `--insecure` in production.

**Fix:** Provide the CA bundle:
```bash
mc --config-dir ~/.mc --certs-dir /path/to/certs alias set ...
```
Or set `SSL_CERT_FILE=/path/to/ca.pem` environment variable.

### Multipart upload fails halfway through

**Cause options:**
1. Part size mismatch — provider has a lower maximum part size than mc is using
2. Server-side error during part upload
3. Connection interrupted during large upload

**Check:**
```bash
mc cp --debug large-file.bin myalias/bucket/ 2>&1 | grep "part\|multipart"
```

**Configuration:**
```bash
# Set part size (default 128 MiB)
mc cp --part-size 64MiB large-file.bin myalias/bucket/
```

### Concurrent copy causes throttling (429)

**Cause:** `mc mirror` or `mc cp --recursive` uses high concurrency by default.

**Limit concurrency:**
```bash
mc cp --recursive --limit-upload 100MiB source/ dest/
mc mirror --limit-download 200MiB --limit-upload 100MiB source/ dest/
```

### `mc: <ERROR> Object is not multipart` during `mc cp`

**Cause:** Trying to use `mc cp` with source and destination on different storage
systems where the object was originally uploaded as a single part but mc is
trying to use server-side copy with a multipart destination.

**Workaround:** Force a local copy through the client machine.

---

## Debug Mode

```bash
mc --debug <command> 2>&1 | tee mc-debug.log
```

Always redact `accessKey`, `secretKey`, `Authorization` in debug output before sharing.

---

## Useful Evidence Commands

```bash
# Check mc version
mc --version

# Test alias connectivity
mc admin info myalias 2>&1   # MinIO-specific
mc ls myalias 2>&1           # S3-compatible

# Check network latency to endpoint
mc ping myalias

# List uploads (check for stuck multipart)
# manual-only: mc ls --incomplete myalias/bucket/

# Check transfer bandwidth
mc cp --benchmark myalias/bucket/

# Show all aliases (redact before sharing)
mc alias list
```

---

## mc vs AWS CLI Feature Differences

| Feature | mc | aws s3 |
|---|---|---|
| Concurrent uploads | Yes (default) | Yes (multipart) |
| Mirror with delete | `mc mirror --remove` | `aws s3 sync --delete` |
| Progress bar | Yes | Yes |
| Bandwidth throttle | `--limit-upload` | No native throttle |
| MinIO admin commands | Yes | N/A |
| S3 Select | No | Yes |
| Object Lock | Partial | Yes |

---

## Version Notes

mc releases frequently. Check for updates if encountering unexpected errors:
```bash
mc update
```
Older mc versions may have bugs with specific S3-compatible providers. Always check
the mc GitHub releases for known issues before diagnosing.
