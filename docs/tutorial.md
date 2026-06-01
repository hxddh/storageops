# StorageOps Tutorial

## Quick Start (5 minutes)

### Step 1 — Install

```bash
# Install Pi Coding Agent
curl -fsSL https://raw.githubusercontent.com/hxddh/storageops/main/scripts/install-pi.sh | bash

# Clone StorageOps
git clone https://github.com/hxddh/storageops.git ~/.pi/storageops
```

### Step 2 — Start the REPL

```bash
cd ~/.pi/storageops
pi --skills ./skills
```

Or use the thin CLI:

```bash
storageops
```

### Step 3 — Describe your issue

Just type naturally:

```
> I'm getting 403 AccessDenied on my bucket. The bucket policy is:
> {
>   "Version": "2012-10-17",
>   "Statement": [...]
> }
```

### Step 4 — Read the diagnosis

The agent will produce a structured diagnosis with:
- Root cause classification
- Evidence from provided logs/policies
- Severity assessment
- Actionable recommendations

## Scenario Walkthroughs

### Scenario 1: s5cmd 429 SlowDown

**Symptom**: s5cmd sync returns 429 SlowDown, then slows down

**Ask**:
```
> My s5cmd sync is getting 429 errors when syncing to BOS.
> [paste s5cmd log output]
```

**What happens**:
1. `scan_secrets` redacts any credentials in the log
2. `detect_domain` matches "performance-throttling" domain (429, SlowDown keywords)
3. `storageops-performance-diagnosis` skill activates
4. Agent analyzes the log pattern and recommends: reduce concurrency, adjust part-size, add --max-retries

### Scenario 2: rclone corrupted on transfer

**Symptom**: rclone mount shows "corrupted on transfer" for large files

**Ask**:
```
> rclone mount keeps failing with "corrupted on transfer" when syncing big files > 500MB.
> [paste rclone -vv log]
```

**What happens**:
1. Credentials redacted
2. Domain detected as "cli-sdk" (rclone + corrupted keywords)
3. `storageops-cli-sdk-diagnosis` skill activates
4. Agent identifies ETag mismatch pattern caused by multipart copy on different providers
5. Recommendation: add `--s3-use-multipart-etag` or `--no-check-certificate`

### Scenario 3: IAM Policy Denied

**Symptom**: KMS-encrypted object access returns AccessDenied

**Ask**:
```
> I'm getting AccessDenied when accessing a KMS-encrypted object. Here's my IAM policy:
> [paste policy JSON]
```

**What happens**:
1. Credentials redacted
2. Domain detected as "security-iam-policy"
3. `storageops-security-iam-policy` skill activates
4. Agent finds missing `kms:Decrypt` permission
5. Recommendation: add KMS key policy allowing decryption

## Tips

- **Paste logs directly**: No need to pre-parse or format — the AI reads raw log output
- **Multi-line input**: Use `\` at the end of a line to continue input, or use `/editor`
- **Shell commands**: Prefix commands with `$` to run them inline: `$ ls -la ~/logs/`
- **File references**: Use `@filename` to reference log files: `@s5cmd-debug.log`
- **Session resume**: `pi --resume <session-id>` to continue a previous session
