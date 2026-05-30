# bcecmd (Baidu Cloud Edge CMD) Analysis

bcecmd is the official CLI tool for Baidu Object Storage (BOS).

## Version Check
```bash
bcecmd --version
```

## Key Configuration

- `~/.bce/credentials` — AK/SK in plaintext (**REDACT in all output**).
- `~/.bce/config` — Region, endpoint, multipart settings.
- Configuration format:
```
[credentials]
ak = [REDACTED]
sk = [REDACTED]

[config]
region = bj
endpoint = bj.bcebos.com
multi_upload_thread_num = 5
memory_unit = MB
```

## Debug Output

bcecmd debug mode (if available):
```bash
bcecmd bos ls bos:/bucket --debug
```

Key sections to extract:
- Request URL and Host header
- Authorization header format
- Content-Length and Content-MD5
- Multipart upload threshold and part size
- Response status and headers

## Common bcecmd Issues

### 1. Endpoint Configuration
- BOS endpoints are region-specific: `bj.bcebos.com`, `gz.bcebos.com`, etc.
- Path-style by default: `https://<endpoint>/<bucket>/<key>`.
- Virtual-hosted style: `https://<bucket>.<endpoint>` (may require DNS setup).

### 2. SigV4 Compatibility
- BOS uses its own signing algorithm similar to but not identical to AWS SigV4.
- Using bcecmd against non-BOS S3 endpoints usually fails with signature errors.
- Using awscli against BOS may require specific configuration.

### 3. Multipart Upload
- Default multipart threshold: typically 5 MB.
- Default part size: typically 5 MB.
- Maximum parts: varies by version.
- bcecmd may retry individual parts on failure.

### 4. Content-MD5
- bcecmd may compute and send Content-MD5 for integrity.
- Some operations require Content-MD5.

### 5. Listing Behavior
- `bcecmd bos ls bos:/bucket/prefix/` — supports prefix and delimiter.
- Pagination model may differ from AWS S3.

## Debug Output Secrets

**CRITICAL:** bcecmd debug output often includes the full Authorization header
containing signed signature components derived from AK/SK. Always redact:
- `Authorization:` header
- `ak = ` line in credentials
- `sk = ` line in credentials
- Any field matching `/^[A-Za-z0-9]{20,}$/` that appears to be a credential
