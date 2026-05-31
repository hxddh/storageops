# S3 Error Code Encyclopedia

## 403 Group — Access & Auth Denied

| Error Code | HTTP | Primary Skill | Root Cause | Common Fix |
|-----------|------|--------------|------------|------------|
| `AccessDenied` | 403 | security-iam-policy | IAM/bucket policy, ACL, KMS, Block Public Access | Check policy evaluation, run policy-permission-evaluator.py |
| `SignatureDoesNotMatch` | 403 | s3-protocol-compatibility | Wrong credentials, clock skew, region mismatch, path/virtual-host mismatch | Check clock skew (<15min), verify endpoint/region, check provider-quirks |
| `InvalidAccessKeyId` | 403 | security-iam-policy | AK does not exist or is deleted | Verify AK in ~/.aws/credentials; check `source scripts/credential-loader.sh` |
| `RequestTimeTooSkewed` | 403 | s3-protocol-compatibility | Client clock differs from server by >15min | Sync NTP: `ntpdate -q <server>`; check `date -u` |
| `AllAccessDisabled` | 403 | security-iam-policy | Account suspended or billing issue | Check account status, billing |
| `AccessForbidden` | 403 | security-iam-policy | KMS key policy denies access | Check KMS key grant for the caller principal |
| `InvalidToken` | 403 | security-iam-policy (sts) | STS session token expired or malformed | Regenerate STS token; check expiration |

## 404 Group — Not Found

| Error Code | HTTP | Primary Skill | Root Cause | Common Fix |
|-----------|------|--------------|------------|------------|
| `NoSuchKey` | 404 | cli-sdk-diagnosis | Object does not exist at specified key | Verify key path, check for trailing slashes, check versioning/delete markers |
| `NoSuchBucket` | 404 | cli-sdk-diagnosis | Bucket does not exist or wrong region | Verify bucket name and region |
| `NoSuchVersion` | 404 | replication-versioning | Specific version ID does not exist | List versions to find valid IDs |
| `NoSuchUpload` | 404 | s3-protocol-compatibility | Multipart upload ID expired or invalid | Check upload lifecycle (abort after 7d recommended) |
| `NotFound` | 404 | s3-protocol-compatibility | Generic not found, varies by provider | Check provider-quirks reference |

## 409 Group — Conflict

| Error Code | HTTP | Primary Skill | Root Cause | Common Fix |
|-----------|------|--------------|------------|------------|
| `BucketAlreadyExists` | 409 | cli-sdk-diagnosis | Bucket name globally taken | Choose different bucket name |
| `BucketAlreadyOwnedByYou` | 409 | cli-sdk-diagnosis | You already own this bucket in another region | Use existing bucket or delete and recreate |
| `OperationAborted` | 409 | s3-protocol-compatibility | Concurrent conflicting write to same key | Retry with backoff |
| `InvalidBucketState` | 409 | replication-versioning | Versioning/Object Lock prevents operation | Check bucket settings before modifying |

## 412 Group — Precondition Failed

| Error Code | HTTP | Primary Skill | Root Cause | Common Fix |
|-----------|------|--------------|------------|------------|
| `PreconditionFailed` | 412 | s3-protocol-compatibility | ETag/If-Match condition not met | Verify ETag is current (object may have changed) |

---

## Provider-Specific Error Discrepancies

### BOS (Baidu)
| BOS Error | AWS Equivalent | Notes |
|-----------|---------------|-------|
| `SignatureDoesNotMatch` | Same | May appear even with correct AK/SK due to proprietary signing |
| `InvalidURI` | `NoSuchKey` | BOS-specific; check URI format |
| `EntityTooLarge` | `EntityTooLarge` | 5GB limit per PUT (same as AWS) |

### OSS (Alibaba)
| OSS Error | AWS Equivalent | Notes |
|-----------|---------------|-------|
| `AccessDenied` | Same | May also indicate wrong endpoint/region |
| `CallbackFailed` | N/A (OSS-specific) | Upload callback to customer server failed — check callback URL |
| `SymlinkTargetNotExist` | N/A (OSS-specific) | Symlink target deleted |

### COS (Tencent)
| COS Error | AWS Equivalent | Notes |
|-----------|---------------|-------|
| `AccessDenied` | Same | COS may return this for non-existent buckets (not `NoSuchBucket`) |
| `InvalidDigest` | `InvalidDigest` | Content-MD5 mismatch |
| `RequestTimeout` | `RequestTimeout` | Network timeout — may be COS server or network path |

---

## 503/429 Group — Throttling & Server

| Error Code | HTTP | Primary Skill | Root Cause | Common Fix |
|-----------|------|--------------|------------|------------|
| `SlowDown` | 503 | performance-diagnosis | Request rate exceeds account/bucket/partition limit | Reduce concurrency, add exponential backoff, distribute prefixes |
| `ServiceUnavailable` | 503 | performance-diagnosis or network-endpoint-access | Server overload or temporary outage | Retry with backoff; check provider status page |
| `InternalError` | 500 | performance-diagnosis | Server-side error (retryable) | Retry; if persistent, contact provider support |
| `RequestRateLimitExceeded` | 429 | performance-diagnosis | Per-IP or per-account rate limit hit | Reduce concurrency, check proxy/NAT shared IP |
| `ThrottlingException` | 429 | performance-diagnosis | Rate limit (AWS DynamoDB-style S3 throttling) | Same as SlowDown |

## Special Codes

| Error Code | HTTP | Primary Skill | Context | Common Fix |
|-----------|------|--------------|---------|------------|
| `IncompleteBody` | 400 | cli-sdk-diagnosis | Request body truncated (network issue) | Check network stability, retry |
| `InvalidPart` | 400 | s3-protocol-compatibility | Multipart part number or ETag wrong | Verify all parts included in CompleteMultipartUpload XML |
| `InvalidPartOrder` | 400 | s3-protocol-compatibility | Part numbers not sequential | Ensure parts numbered 1..N |
| `EntityTooLarge` | 400 | cli-sdk-diagnosis | Object exceeds max size (5GB single PUT / 5TB multipart) | Use multipart for >5GB |
| `MalformedXML` | 400 | cli-sdk-diagnosis | Request body XML invalid | Check XML structure (typo, missing tag) |
| `MaxMessageLengthExceeded` | 400 | cli-sdk-diagnosis | DeleteObjects request too large (>1000 objects) | Batch into 1000-object groups |
| `InvalidRange` | 416 | cli-sdk-diagnosis | Range header invalid (byte range out of bounds) | Verify object size before setting range |

## How to Use This Reference

When diagnosing, match the error code in the response to the table above:
1. Identify the primary skill to invoke
2. Check provider-quirks if using non-AWS provider
3. Follow the "Common Fix" path
4. If error code is provider-specific (not in this table), check provider documentation directly
