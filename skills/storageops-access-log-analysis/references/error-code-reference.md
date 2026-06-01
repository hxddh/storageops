# Error Code Reference — Object Storage Access Logs

Cross-provider error code semantics, grouped by category. Error codes with the same name may have provider-specific nuances.

## Authorization Errors

| Error Code | S3 | BOS | OSS | COS |
|-----------|-----|-----|-----|-----|
| `AccessDenied` | IAM/bucket policy | AK/SK or bucket policy | RAM policy or bucket policy | CAM policy or bucket policy |
| `SignatureDoesNotMatch` | Wrong SK, region | Wrong AK/SK | Wrong AK/SK | Wrong SecretId/Key |
| `InvalidAccessKeyId` | AK doesn't exist | AK disabled/expired | AK doesn't exist | SecretId doesn't exist |
| `RequestTimeTooSkewed` | Clock > 15 min | Clock drift | Clock > 15 min | Clock skew |
| `ExpiredToken` | STS token expired | - | - | STS token expired |

## Resource Errors

| Error Code | S3 | BOS | OSS | COS |
|-----------|-----|-----|-----|-----|
| `NoSuchKey` | Object missing | Object missing | Object missing | Object missing |
| `NoSuchBucket` | Bucket missing | Bucket missing | Bucket missing | Bucket missing |
| `BucketAlreadyExists` | Name conflict | Name conflict | Name conflict | Name conflict |
| `ObjectLocked` | WORM retention | - | - | WORM retention |

## Throttling & Service Errors

| Error Code | S3 | BOS | OSS | COS |
|-----------|-----|-----|-----|-----|
| `SlowDown` | Partition limit | Rate limit | Rate limit | Rate limit |
| `InternalError` | Transient (retry) | - | - | - |
| `ServiceUnavailable` | Overload | Overload | - | Overload |
| `RequestTimeout` | Connection timeout | Request timeout | - | - |

## Special Codes

| Error Code | S3 | BOS | OSS | COS |
|-----------|-----|-----|-----|-----|
| `PreconditionFailed` | ETag/condition failed | - | ETag condition | - |
| `NotModified` | Conditional GET (304) | - | Conditional GET | - |
| `TemporaryRedirect` | 307 redirect | - | - | - |
| `PermanentRedirect` | Wrong region | Wrong region | - | - |

## Diagnostic Quick Guide

**403 spike**: Cross-reference with IAM/policy changes. Check requester field for new IPs/roles.
**404 spike on existing objects**: Lifecycle rule deleted objects, wrong prefix in client code.
**503/SlowDown spike**: Partition hot-key or burst rate exceeded. Route to performance-diagnosis.
**SignatureDoesNotMatch**: Clock skew on client machine, wrong region in signing logic.
