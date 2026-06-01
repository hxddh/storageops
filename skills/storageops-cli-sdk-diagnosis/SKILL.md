---
name: storageops-cli-sdk-diagnosis
description: >
  Diagnose errors from object storage CLI tools and SDKs (s5cmd, rclone, aws
  CLI, boto3, minio client, s3cmd, bcecmd, obsutil). Covers tool-specific bugs,
  version incompatibilities, configuration mistakes, and cross-tool behavioral
  differences. Use when user reports errors from a specific client tool or SDK.
maturity: stable
mode: light_heavy
estimated_tokens: 1400
trigger_keywords:
  - s5cmd
  - rclone
  - aws CLI
  - boto3
  - minio client
  - s3cmd
  - bcecmd
  - obsutil
  - CLI error
  - SDK error
  - botocore
  - tool version
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# CLI & SDK Diagnosis

Tool-specific known issues: s5cmd 429 handling, rclone multipart ETag incompatibility with BOS, boto3 clock skew, aws CLI signature version defaults. Cross-reference the tool's reference file for detailed patterns.

## Decision Tree

```
CLI/SDK error →
  ├─ s5cmd? → Check `references/s5cmd.md`
  │   ├─ 429 SlowDown? → Concurrency too high (default 256 workers)
  │   └─ SignatureDoesNotMatch? → Clock skew or wrong region
  ├─ rclone? → Check `references/rclone.md`
  │   ├─ multipart upload corruption? → ETag format mismatch (BOS vs AWS)
  │   └─ "directory not found"? → rclone VFS cache issue
  ├─ aws CLI? → Check `references/awscli.md`
  │   ├─ SignatureDoesNotMatch? → Clock skew >5 min
  │   └─ SSL/TLS error? → ca-certificates or proxy
  ├─ boto3/botocore? → Check `references/boto3-botocore.md`
  │   ├─ ClientError 403? → Region mismatch or credential chain
  │   └─ EndpointConnectionError? → Endpoint URL format
  ├─ s3cmd/minio-client? → Check respective reference
  ├─ bcecmd (Baidu)? → Check `references/bcecmd.md`
  └─ obsutil (Huawei)? → Check `references/obsutil.md`
```

## Workflow

### Step 1: Identify Tool + Version
Extract tool name, version, and command used. If version is unknown, ask — many bugs are version-specific.

### Step 2: Parse the Error
Extract error code, error message, and any timing data or stack trace. Compare against known issues in the tool's reference file.

### Step 3: Check Configuration
Common misconfigurations: wrong endpoint URL, wrong region, wrong signature version (v2 vs v4), proxy settings interfering, clock skew (>5 min causes signature failure).

### Step 4: Cross-Tool Comparison
If multiple tools are mentioned: does the same operation fail with a different tool? This isolates tool-specific bugs from service-side issues.

### Step 5: Apply Known Fix
Consult the tool's reference file for known workarounds. These are the most reliable fixes.

## Output Format

```markdown
# Diagnosis: [tool] — [one-line]
**Tool**: [name] [version]
**Root cause**: tool-bug | tool-version-incompatibility | misconfiguration | clock-skew | provider-incompatibility
**Confidence**: high | medium | low

## Evidence
- Error: [code + message]
- Command: [sanitized]
- Tool version: [known/unknown]

## Known Issue Match
[Link to known issue in tool's reference or explanation of why it matches]

## Fix
1. **[specific config/flag change]** — [rationale]
2. **[workaround]** — [if applicable]

## Cross-Tool Verification
[If applicable: does aws CLI succeed where rclone fails?]
```

## Examples

### Example 1: rclone multipart corruption on BOS
**Input**: rclone copy to BOS, files >5GB corrupted. No error, but checksums don't match.
**Diagnosis**: rclone multipart ETag format incompatibility — BOS uses different ETag format for multipart uploads (no `-N` suffix). rclone's integrity check fails.
**Fix**: `--s3-use-multipart-etag=false` on rclone command. Or `--ignore-checksum` as temporary workaround.

### Example 2: s5cmd 429 SlowDown
**Input**: s5cmd sync with default settings, 256 workers, getting `SlowDown (429)`.
**Diagnosis**: Default concurrency (256) exceeds BOS rate limit for prefix.  
**Fix**: `--concurrency 16 --retry-count 10`. Reduce further if 429 persists. BOS per-prefix limit is lower than AWS S3.

### Example 3: aws CLI clock skew
**Input**: `aws s3 ls` returns `SignatureDoesNotMatch: Signature expired`.
**Diagnosis**: Local clock >15 min off from server time. AWS SigV4 signs with timestamp.
**Fix**: `ntpdate -u ntp.aliyun.com` or `sudo ntpdate ntp.aliyun.com`. Verify with `date -u`.

## References
- `references/s5cmd.md` — s5cmd-specific known issues, concurrency defaults
- `references/rclone.md` — rclone S3 backend quirks, ETag, VFS
- `references/awscli.md` — AWS CLI configuration, clock skew, proxy
- `references/boto3-botocore.md` — Python SDK credential chain, retries
- `references/s3cmd.md` — s3cmd signing and compatibility
- `references/minio-client.md` — mc (minio client) quirks
- `references/bcecmd.md` — Baidu BOS CLI specifics
- `references/obsutil.md` — Huawei OBS CLI specifics
