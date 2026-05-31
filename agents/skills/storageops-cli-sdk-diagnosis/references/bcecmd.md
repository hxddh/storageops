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
bcecmd bos cp <local> bos:/bucket/key --debug
```

### Debug Log Parsing Guide

Key sections to extract:

**Request identification:**
```
Request URL: https://<endpoint>/<bucket>/<key>
Method: GET/PUT/DELETE
Host Header: <bucket>.<endpoint> or <endpoint>
```

**Authorization header (REDACT before sharing):**
```
Authorization: bce-auth-v1/<ak>/<timestamp>/<expiration>/<signed-headers>/<signature>
```
- Format differs from AWS SigV4: uses `bce-auth-v1` instead of `AWS4-HMAC-SHA256`
- Timestamp format: ISO 8601
- Signed headers: may include `host`, `x-bce-date`, `x-bce-content-sha256`

**Multipart upload tracking:**
```
InitiateMultipartUpload: UploadId=<id>
UploadPart: PartNumber=<N>, ContentLength=<bytes>
CompleteMultipartUpload: Parts=<count>
```

**Response:**
```
HTTP/<version> <status>
x-bce-request-id: <uuid>
Content-Type: application/json or application/xml
```

**Timing (if available):**
```
Elapsed time: <N>ms
DNS lookup: <N>ms, TCP connect: <N>ms, TLS handshake: <N>ms
```

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
- Default `max-keys`: 1000.
- Marker-based pagination (not continuation-token).

### 6. Common Error Patterns
| Error | Typical Cause | Fix |
|-------|--------------|-----|
| `SignatureDoesNotMatch` | Wrong AK/SK or clock skew | Verify credentials, sync NTP |
| `InvalidAccessKeyId` | AK deleted or rotated | Check BOS console |
| `NoSuchBucket` | Wrong region or bucket name | Verify region in `~/.bce/config` |
| `AccessDenied` | IAM/bucket policy | Check BOS IAM console |
| `EntityTooLarge` | Object >5GB (single PUT) | Use multipart upload |
| `InvalidURI` | Malformed object key | Check URL encoding, special chars |

### 7. bcecmd vs awscli Comparison
| Scenario | bcecmd | awscli against BOS |
|----------|--------|-------------------|
| Authentication | Native BOS signing | Must configure SigV4 compat |
| Multipart default | 5MB threshold | 8MB threshold |
| Debug verbosity | `--debug` flag | `--debug` flag |
| Path style | Default | Required for non-AWS |
| Region config | `~/.bce/config` | `--region` flag |
| Works against non-BOS? | ❌ No (proprietary signing) | ⚠️ May work with config |

## Performance Tuning

```bash
# Increase multipart threads for faster upload
~/.bce/config: multi_upload_thread_num = 10

# Increase part size for larger files
~/.bce/config: multi_upload_part_size = 10  # MB

# Disable CRC check for speed (warning: integrity risk)
# Do NOT use in production
```

## Debug Output Secrets

**CRITICAL:** bcecmd debug output often includes the full Authorization header
containing signed signature components derived from AK/SK. Always redact:
- `Authorization:` header
- `ak = ` line in credentials
- `sk = ` line in credentials
- Any field matching `/^[A-Za-z0-9]{20,}$/` that appears to be a credential
