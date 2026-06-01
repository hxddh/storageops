# s3cmd Diagnosis

## Overview

s3cmd is a Python command-line tool for S3-compatible storage, widely used in
Linux environments. It uses its own SigV4 implementation and config file format
(`~/.s3cfg`). Common issues: signature errors with non-AWS endpoints, path-style
vs virtual-hosted-style mismatches, SSL certificate errors, and multipart thresholds.

---

## Configuration File

`~/.s3cfg` — key fields for diagnosis:

```ini
[default]
access_key = AKIAIOSFODNN7EXAMPLE        # AK
secret_key = wJalrXUtnFEMI/K7MDENG/bPx  # SK — redact before sharing
host_base = s3.amazonaws.com             # endpoint hostname
host_bucket = %(bucket)s.s3.amazonaws.com  # virtual-hosted style pattern
use_https = True                         # must be True for S3
signature_v2 = False                     # must be False for SigV4
check_ssl_certificate = True
check_ssl_hostname = True
multipart_chunk_size_mb = 15             # part size for multipart uploads
```

**Critical for non-AWS providers:**
- `host_base` — set to provider's endpoint hostname
- `host_bucket` — set to `%(bucket)s.<provider-endpoint>` for virtual-hosted style,
  or `<provider-endpoint>/%(bucket)s` for path style
- `signature_v2 = False` — must be False; some old providers need True (SigV2)

---

## Common Errors and Root Causes

### `ERROR: S3 error: 403 (InvalidAccessKeyId)`

**Cause:** Access key not found by the provider.

**Check:**
1. Confirm `access_key` in `~/.s3cfg` matches the provider's AK exactly (no leading/trailing spaces)
2. Confirm the key belongs to the correct account/project for this endpoint

### `ERROR: S3 error: 403 (SignatureDoesNotMatch)`

**Cause options:**
1. `signature_v2 = True` set but provider requires SigV4 → set `signature_v2 = False`
2. Clock skew > 15 minutes → sync system clock with NTP
3. `host_base` or `host_bucket` mismatch causing wrong canonical URI
4. `use_https = False` with an HTTPS-only endpoint

**Diagnosis:**
```bash
s3cmd --debug ls s3://bucket/ 2>&1 | grep -A 10 "StringToSign\|Canonical"
```

### `WARNING: Certificate verification failure`

**Cause:** Custom endpoint with self-signed or internal CA certificate.

**Do NOT** use `check_ssl_certificate = False` in production.

**Fix:** Add the CA certificate:
```ini
ca_certs_file = /path/to/your-ca.pem
```

### Multipart upload stalls on large files

**Cause:** `multipart_chunk_size_mb` too large or too small for the endpoint.

Common provider limits:
- Most providers: 5 MB minimum part size
- Maximum parts: 10,000
- Recommended: 15–100 MB per part for large files

**Check:** Does the provider accept the current part size?
```bash
s3cmd --debug put large-file.bin s3://bucket/ 2>&1 | grep "multipart\|part size"
```

### `ERROR: [Errno 104] Connection reset by peer` on large uploads

**Cause:** MTU mismatch on the network path. Large TCP segments are silently dropped.

**Workaround:** Reduce `multipart_chunk_size_mb` to 8–15 MB. This doesn't fix the
underlying MTU issue but reduces segment sizes enough to avoid the black hole.

---

## Debug Mode

```bash
s3cmd --debug <command> 2>&1 | tee s3cmd-debug.log
```

Debug output includes: canonical request, string to sign, request URL, response headers, response body.

Always redact `access_key`, `secret_key`, `Authorization` before sharing debug logs.

---

## Path-Style vs Virtual-Hosted-Style

s3cmd's `host_bucket` setting controls the URL format:
- Virtual-hosted: `%(bucket)s.s3.example.com` → `bucket.s3.example.com/key`
- Path-style: `s3.example.com/%(bucket)s` → `s3.example.com/bucket/key`

Some providers only support path-style. To use path-style:
```ini
host_bucket = s3.example.com/%(bucket)s
```

Note: AWS S3 deprecated path-style access for new buckets since 2020. Use
virtual-hosted style for AWS.

---

## Common Commands for Evidence Collection

```bash
# List buckets (tests AK/SK and endpoint)
s3cmd --debug ls 2>&1 | head -50

# Get s3cmd version
s3cmd --version

# Show current config (redact secrets)
s3cmd --dump-config | grep -v secret_key | grep -v access_key

# Test connectivity to endpoint
curl -v https://<host_base>/ 2>&1 | head -30
```

---

## Version Notes

s3cmd v2.x added better SigV4 support. If on v1.x, upgrade:
```bash
pip install --upgrade s3cmd
s3cmd --version
```
