# StorageOps Tutorial

## Quick Start (5 minutes)

### Step 1 — Install and set up

```bash
pip install storageops
storageops setup
```

`setup` downloads Pi Coding Agent, asks for your LLM provider and API key, and saves
them to `~/.storageops/config.json`.

### Step 2 — Start the REPL

```bash
storageops
```

Describe your problem in plain language. No need to know skill names — the agent routes automatically.

```
StorageOps  S3 Diagnostic Agent
Describe your issue or paste error logs.

> rclone reports "corrupted on transfer" after copying large files to S3
```

### Step 3 — Provide evidence

The agent tells you what evidence it needs and how to collect it. Paste log output directly,
or reference a file with `@`:

```
> here is the rclone debug log @/tmp/rclone-vv.log
```

### Step 4 — Read the report

The agent outputs a structured diagnosis:

```markdown
---
category: s3_protocol_compatibility
root_cause_type: multipart_etag_format_mismatch
confidence: 0.92
severity: high
---
## Summary
rclone's multipart ETag is an MD5 of part-MD5s (not the full object MD5),
which doesn't match the server's ETag on verification.

## Remediation
# manual-only: rclone --s3-upload-cutoff 5G copy src remote:bucket
```

---

## Scenario Walkthroughs

### 403 AccessDenied on GetObject

```
> s3://my-bucket/data/file.csv — AccessDenied, but my IAM role has s3:GetObject
```

What StorageOps checks:
- Does the policy grant `s3:GetObject` on the **bucket ARN** but miss the `/*` suffix
  for objects?
- Is there a bucket policy with an explicit `Deny`?
- Is there an SCP at the organization level?
- Is a VPC endpoint condition restricting access?

Typical output: corrected policy snippet with the missing resource qualifier added.

### Slow uploads — throttling or bandwidth?

```
> AWS S3 uploads only hitting 20 MB/s, expected 200 MB/s
> here's the rclone log @rclone-vv.log
```

What StorageOps checks:
1. 429/SlowDown errors → throttling from prefix hotspot
2. Multipart part size and concurrency settings vs bandwidth-delay product
3. Client CPU or disk I/O as bottleneck
4. TLS handshake overhead on small files

### SignatureDoesNotMatch on MinIO

```
> MinIO returns SignatureDoesNotMatch but the same command works on AWS S3
```

What StorageOps checks:
- Clock skew (request timestamp vs server time)
- Path-style vs virtual-hosted-style endpoint mismatch
- SigV4 region in the credential scope vs the endpoint region
- Provider quirks documented in `references/provider-quirks/minio.md`

### rclone corrupted on transfer

```
> rclone copy to BOS says "corrupted on transfer" for files > 5 GB
```

Root cause (most common): rclone uses multipart upload for large files; the resulting ETag
is `MD5(part-MD5s)-N`, not `MD5(full-object)`. If BOS is returning the object MD5, the
comparison fails.

Fix:
```bash
# manual-only: set upload cutoff above the largest file to force single-part upload
rclone copy src bos:bucket --s3-upload-cutoff 10G

# Or: disable ETag verification (loses integrity check)
# manual-only: rclone copy src bos:bucket --checksum=false
```

### VPC endpoint unreachable

```
> inside our VPC, aws s3 ls times out — works fine from my laptop
```

What StorageOps checks:
- Does the VPC endpoint have Private DNS enabled? (If not, DNS resolves to a public IP)
- Is there a route table entry for the endpoint?
- Does the security group allow HTTPS (443) to the endpoint?

### Browser CORS error

```
> JavaScript in the browser gets "No 'Access-Control-Allow-Origin' header" on PutObject
```

What StorageOps checks:
- Does the bucket CORS configuration list the request origin in `AllowedOrigins`?
- Does it include `PUT` in `AllowedMethods`?
- Is the S3 CORS preflight (OPTIONS) returning the correct headers?

---

## Using httpmon for Wire-Level Evidence

[httpmon](https://github.com/hxddh/https-traffic-inspector) wraps any CLI command and
captures full HTTP/HTTPS traffic. Pipe the output to StorageOps for the most precise diagnosis.

```bash
# Install httpmon
go install github.com/hxddh/https-traffic-inspector@latest

# Capture and pipe directly to StorageOps
httpmon --format json aws s3 cp s3://bucket/key . 2>&1 | storageops

# Capture to HAR, then diagnose
httpmon --har capture.har rclone copy remote:bucket/ ./local/
storageops @capture.har
```

httpmon reveals what tool logs hide: the full error XML body, exact Authorization header
format, per-request TTFB timing, and complete CORS preflight headers.

---

## Session Resume

StorageOps saves every session automatically to `~/.storageops/sessions/`.
Type `/resume` inside a session to see a numbered list of past sessions and load one.

---

## One-Shot and CI Mode

```bash
# Pipe a log file
storageops < error.log

# CI: exit 1 on high/critical severity
storageops diagnose error.log --exit-code

# JSON output for scripting
storageops triage error.log --format json
```

---

## FAQ

**Q: Where do I start?**
Describe your symptom to the REPL (`storageops`). The agent routes to the correct skill.
If uncertain, it runs triage first.

**Q: What evidence should I provide?**
At minimum: error message/status code + tool + provider/endpoint. More is better.
The agent tells you what it needs to increase confidence.

**Q: Why is confidence only 0.5?**
Insufficient evidence. The agent lists what's missing. Provide more evidence and the
confidence goes up. Low confidence = honest, not wrong.

**Q: Will StorageOps modify my bucket?**
No. All dangerous operations are labeled `manual-only` and require your explicit action.
StorageOps is purely read-only and diagnostic.

**Q: Which providers are supported?**
AWS S3 (baseline), Alibaba Cloud OSS, Baidu Cloud BOS, Tencent Cloud COS, Volcengine TOS,
MinIO, Ceph, Wasabi, and other S3-compatible endpoints.

**Q: Which tools are supported?**
rclone, AWS CLI, s5cmd, boto3/botocore, MinIO Client (mc), s3cmd. Each has a dedicated parser.

**Q: What are the absolute limits?**
1. Never reads credential files  
2. Never recommends public access  
3. Never disables TLS  
4. Never executes write operations automatically  
5. Never fabricates evidence
