# awscli Debug Log Analysis

## Scope

This reference applies to the AWS CLI (`aws`) and its botocore-based command
execution. Do not apply these config paths directly to rclone, s5cmd, bcecmd, or
application SDKs unless the user's tool explicitly uses the AWS shared config and
credential chain.

## Verify Before Applying

Confirm the active CLI, profile, and credential source before recommending a
path:

```bash
aws --version
aws configure list
aws configure list-profiles
```

## Version Check
```bash
aws --version
```
Output example: `aws-cli/2.15.0 Python/3.11.6 Darwin/23.0.0 source/arm64`

## Key Configuration

- `~/.aws/config` — Region, output format, retry mode.
- `~/.aws/credentials` — AK/SK, session token (REDACT in output).
- Environment: `AWS_DEFAULT_REGION`, `AWS_PROFILE`, `AWS_CA_BUNDLE`.

## Debug Output (`--debug`)

awscli `--debug` produces extremely verbose output. Key sections to extract:

### Credentials Resolution
```
CredentialsProvider: ...
Loading credentials from ...
Found credentials in ...
```
Check: Is the right profile being used? Is the session token present and not expired?

### Request Construction
```
Making request for OperationModel(name=ListObjectsV2) ...
Endpoint: https://<bucket>.<endpoint>
CanonicalRequest: ...
StringToSign: ...
```
Check: Region, endpoint hostname, path-style vs virtual-hosted.

### HTTP Request
```
send_request: POST /<bucket>?uploads
headers: {
    'Host': '<endpoint>',
    'x-amz-content-sha256': '...',
    'Authorization': 'AWS4-HMAC-SHA256 ...'
}
```
**WARNING:** Authorization header contains signature components from the credential chain. REDACT the full header value.

### Response
```
Response headers: {'x-amz-request-id': '...', 'content-type': 'application/xml'}
Response body: <?xml version="1.0" ...>
```
Check: Status code, error code, request ID.

### Retries
```
Retry needed, retrying attempt N after M seconds
```
Check: Retry reason (throttling, connection error, server error), retry count, backoff duration.

## Common awscli Issues

### 1. Endpoint URL Format
- `--endpoint-url https://s3.example.com` → path-style by default.
- Virtual-hosted-style requires bucket in hostname: `--endpoint-url https://<bucket>.s3.example.com`.
- Some S3-compatible providers only support one style.

### 2. SignatureDoesNotMatch
- Very often clock skew.
- `date -u` on the client machine.
- Compare `Timestamp` in CanonicalRequest with server time.

### 3. Retry Loop
- Default max retries: 5 (standard mode) or 2 (adaptive mode).
- `--cli-read-timeout` and `--cli-connect-timeout` control timeouts.
- Retry on 5xx, throttling, and connection errors.

### 4. Large File Upload
- awscli automatically uses multipart for files > `multipart_threshold` (default 8 MB).
- Part size: `multipart_chunksize` (default 8 MB).
- Concurrency: `max_concurrent_requests` (default 10).

## Debug Log Extraction Commands

```bash
# Extract only errors
grep -i "error\|fail\|denied\|throttl" <debug-log>

# Extract canonical request (redact after)
grep -A 30 "CanonicalRequest:" <debug-log>

# Extract timing
grep -E "send_request|receive_response|retry" <debug-log>
```
