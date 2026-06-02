# Secret Detection and Redaction

## MUST Redact

The following patterns must ALWAYS be replaced with `[REDACTED]` before outputting
any content to the user or storing in diagnostic reports:

### Access Key ID (AK)
```
Pattern: /AKIA[0-9A-Z]{16}/
Example: AKIAIOSFODNN7EXAMPLE → [REDACTED]
Context: AWS access key IDs (and similar from other providers).
```

### Secret Access Key (SK)
```
Pattern: 40-character alphanumeric strings following AK or in credential files
Context:
- "SecretAccessKey": "[REDACTED]"
- "sk = [REDACTED]"
- "secret_access_key = [REDACTED]"
```

### Session Token
```
Pattern: Long base64-encoded strings (500+ characters)
Context: "SessionToken": "[REDACTED]"
```

### Authorization Header
```
Pattern: /^Authorization: .*$/
Example: Authorization: AWS4-HMAC-SHA256 Credential=.../.../.../s3/aws4_request,
         SignedHeaders=..., Signature=... → Authorization: [REDACTED]
```
**Critical:** The Authorization header contains signature components derived from the
secret key. An attacker with a valid signed request can potentially extract information.

### Presigned URL Query Parameters
```
Pattern: /X-Amz-Signature=[0-9a-f]{64}/
Example: https://...?X-Amz-Signature=abc123... → https://...?X-Amz-Signature=[REDACTED]
```

### Credential File Content
```
- ~/.aws/credentials → Entire file content must be scanned and redacted.
- ~/.go-bcecli/credentials → BOS CMD credential file; scan and redact if present.
- ~/.obsutilconfig → Entire file content must be scanned and redacted.
- rclone config → Output of `rclone config show` must be scanned and redacted.
```

## MAY Contain Secrets (Context-Dependent)

### Cookie / Session Cookie
- HttpOnly cookies in HTTP traces.
- `Set-Cookie:` headers.
- Redact unless explicitly needed for diagnosis.

### JWT / Bearer Tokens
- `Bearer eyJ...` in Authorization headers.
- JWT payloads may contain sensitive information.

### API Keys in Headers
- `x-api-key:` headers.
- Custom authentication headers.

### Connection Strings / URLs with Credentials
```
Pattern: /https?:\/\/[^:]+:[^@]+@/
Example: https://user:password@endpoint.com → https://[REDACTED]@endpoint.com
```

## Redaction Best Practices

### 1. Redact Before Output
- NEVER output raw credentials.
- Scan ALL text before output.
- If unsure, redact.

### 2. Preserve Debug Value Where Possible
- Redact the secret but preserve the structure:
  - `Authorization: [REDACTED]` — Shows the header EXISTS (important for diagnosis).
  - `aws_access_key_id = [REDACTED]` — Shows the key WAS configured.
  - `sk = [REDACTED]` — Shows the secret WAS provided.

### 3. Redact in Code/Config Snippets Too
- When showing configuration examples, use placeholders:
  - `aws_access_key_id = YOUR_ACCESS_KEY`
  - `sk = YOUR_SECRET_KEY`
  - NOT redacted real values.

### 4. Check Multiple Formats
- JSON: `"SecretAccessKey": "[REDACTED]"`
- INI: `aws_secret_access_key = [REDACTED]`
- YAML: `secretAccessKey: [REDACTED]`
- Shell env: `export AWS_SECRET_ACCESS_KEY=[REDACTED]`
- Command line: Not easily detected (passed at runtime).
  - WARNING: Command-line arguments are visible in `ps aux`.

## Edge Cases

### Non-AWS Credential Formats
- BOS: `ak = <string>, sk = <string>` in INI format.
- OSS: `accessKeyID`, `accessKeySecret` in XML/JSON.
- COS: `SecretId`, `SecretKey`.
- MinIO: Same as AWS (AKIA... format).

### Signed Headers in Debug Logs
- `x-amz-date:` — NOT a secret (timestamp).
- `x-amz-content-sha256:` — NOT a secret (content hash).
- `host:` — NOT a secret.
- But `Authorization:` header IS a secret — even the signed form.

### Credentials in HTTP Bodies
- Some S3-compatible providers use non-standard auth (credentials in POST body).
- Scan response AND request bodies.
