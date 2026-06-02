# s5cmd Diagnostic Analysis

s5cmd is a high-performance S3 client written in Go, optimized for parallel operations.

## Scope

This reference applies to `s5cmd` command-line behavior. s5cmd commonly uses
AWS-style environment variables and flags, but it is not awscli, rclone, or an
SDK. Do not transfer config-file assumptions from other tools unless the user's
evidence proves s5cmd is using them.

## Verify Before Applying

Confirm the installed version and active command flags:

```bash
s5cmd version
s5cmd --help | head
```

Ask for the exact command line with secrets redacted.

## Version Check
```bash
s5cmd version
```

## Key Parameters

| Parameter | Default | Notes |
|---|---|---|
| `--endpoint-url` | (required for non-AWS) | S3 endpoint |
| `--numworkers` | 256 | Concurrent goroutines for listing |
| `--concurrency` | 5 | Concurrent requests for upload/download |
| `--part-size` | 5M | Multipart part size |
| `--retry-count` | 10 | Number of retries |
| `--no-sign-request` | false | Skip SigV4 (public buckets only) |
| `--no-verify-ssl` | false | Skip TLS verification (insecure) |
| `--request-payer` | (empty) | Requester-pays header |
| `--dry-run` | false | Print operations without executing |

## Environment Variables
- `S5CMD_ACCESS_KEY_ID` / `AWS_ACCESS_KEY_ID`
- `S5CMD_SECRET_ACCESS_KEY` / `AWS_SECRET_ACCESS_KEY`
- `S5CMD_SESSION_TOKEN` / `AWS_SESSION_TOKEN`
- `S5CMD_REGION` / `AWS_REGION`
- `S5CMD_ENDPOINT_URL`

## Debug Output
```bash
s5cmd --log debug ls s3://bucket/
s5cmd --log debug cp file s3://bucket/key
```

## Common s5cmd Issues

### 1. Concurrency vs Part Size Interaction
- `--concurrency` controls how many concurrent requests (uploads/downloads/download parts).
- `--part-size` controls the size of each multipart part.
- Total bandwidth = concurrency × per-connection throughput.
- Too high concurrency → server-side throttling (429/SlowDown).
- Too low concurrency → underutilized bandwidth.

**Tuning guidance:**
- High-latency links: increase concurrency.
- High-bandwidth links: increase part size.
- Small files: `--part-size` is irrelevant; `--concurrency` dominates.

### 2. `--numworkers` and Listing Performance
- `--numworkers` (default 256) controls goroutines for listing objects.
- Very high values can trigger rate limiting on ListObjects.
- Listing millions of objects with high `--numworkers` may cause 429 errors.
- Reduce `--numworkers` if listing is being throttled.

### 3. Wildcard Expansion
- s5cmd supports wildcards: `s5cmd cp 'dir/*.txt' s3://bucket/prefix/`
- Wildcard expansion happens LOCALLY, not server-side.
- Large directory listings can cause high stat() load on local filesystem.

### 4. Bucket vs Object URL
- `s3://bucket` — bucket-level operations (ls, mb, rb).
- `s3://bucket/key` — object-level operations (cp, rm, mv).
- Trailing slash matters for prefixes during copy.

### 5. Non-AWS S3 Compatibility
- s5cmd supports S3-compatible endpoints via `--endpoint-url`.
- Uses path-style for custom endpoints.
- Some providers reject s5cmd's request format (Content-Type header, etc.).

### 6. Memory Usage with High Concurrency
- s5cmd loads object listings into memory for batch operations.
- `s5cmd cp s3://bucket/prefix/* .` with millions of objects → high memory.
- Use `s5cmd sync` for incremental operations instead of wildcard cp.

## Performance Profiling Commands

```bash
# Time a simple operation
time s5cmd --log debug --concurrency 5 cp largefile s3://bucket/key

# Measure upload with varying concurrency
for c in 1 5 10 20 50; do
    echo "concurrency=$c"
    time s5cmd --concurrency $c cp largefile s3://bucket/key
done
```
