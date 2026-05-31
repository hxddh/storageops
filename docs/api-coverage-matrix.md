# S3 API Operation Coverage Matrix

## Operations by Diagnostic Domain

Each S3 API operation maps to the skill(s) that diagnose its failures.

| S3 API Operation | Primary Skill | Secondary Skill | Coverage Status |
|-----------------|--------------|-----------------|-----------------|
| `GetObject` | performance-diagnosis, cli-sdk-diagnosis | s3-protocol-compatibility, security-iam-policy | ✅ Full |
| `PutObject` | performance-diagnosis, cli-sdk-diagnosis | s3-protocol-compatibility, security-iam-policy | ✅ Full |
| `HeadObject` | performance-diagnosis, mount-filesystem-workspace | security-iam-policy | ✅ Full |
| `DeleteObject` | security-iam-policy | replication-versioning | ✅ Full |
| `DeleteObjects` | security-iam-policy | cli-sdk-diagnosis | ✅ Full |
| `ListObjectsV2` | s3-protocol-compatibility | cli-sdk-diagnosis | ✅ Full |
| `ListObjects` (V1) | s3-protocol-compatibility | cli-sdk-diagnosis | ✅ Full |
| `ListObjectVersions` | replication-versioning | s3-protocol-compatibility | ✅ Full |
| `ListBuckets` | security-iam-policy | cli-sdk-diagnosis | ⚠️ Partial |
| `CreateBucket` | security-iam-policy | cli-sdk-diagnosis | ⚠️ Partial |
| `DeleteBucket` | security-iam-policy | — | ⚠️ Partial |
| `GetBucketLocation` | cli-sdk-diagnosis | network-endpoint-access | ✅ Full |
| `GetBucketVersioning` | replication-versioning | — | ✅ Full |
| `PutBucketVersioning` | replication-versioning | security-iam-policy | ⚠️ Partial |
| `GetBucketPolicy` | security-iam-policy | — | ✅ Full |
| `PutBucketPolicy` | security-iam-policy | — | ⚠️ Partial |
| `DeleteBucketPolicy` | security-iam-policy | — | ⚠️ Partial |
| `GetBucketAcl` | security-iam-policy | — | ⚠️ Partial |
| `PutBucketAcl` | security-iam-policy | — | ⚠️ Partial |
| `GetObjectAcl` | security-iam-policy | — | ⚠️ Partial |
| `PutObjectAcl` | security-iam-policy | — | ⚠️ Partial |
| `PutBucketEncryption` | security-iam-policy | — | ⚠️ No dedicated reference |
| `GetBucketEncryption` | security-iam-policy | — | ⚠️ No dedicated reference |
| `CreateMultipartUpload` | s3-protocol-compatibility | cli-sdk-diagnosis | ✅ Full |
| `UploadPart` | s3-protocol-compatibility | performance-diagnosis | ✅ Full |
| `UploadPartCopy` | s3-protocol-compatibility | cli-sdk-diagnosis | ⚠️ Partial |
| `CompleteMultipartUpload` | s3-protocol-compatibility | cli-sdk-diagnosis | ✅ Full |
| `AbortMultipartUpload` | s3-protocol-compatibility | lifecycle-cost | ✅ Full |
| `ListMultipartUploads` | s3-protocol-compatibility | replication-versioning | ⚠️ Partial |
| `ListParts` | s3-protocol-compatibility | — | ⚠️ Partial |
| `CopyObject` | s3-protocol-compatibility | cli-sdk-diagnosis | ✅ Full |
| `RestoreObject` | lifecycle-cost | — | ⚠️ Partial |
| `GetObjectTorrent` | — | — | ❌ Not Covered |
| `GetBucketWebsite` | — | — | ❌ Not Covered |
| `PutBucketWebsite` | — | — | ❌ Not Covered |
| `GetBucketLogging` | — | — | ❌ Not Covered |
| `PutBucketLogging` | — | — | ❌ Not Covered |
| `GetBucketNotification` | replication-versioning | — | ⚠️ Partial |
| `PutBucketNotification` | replication-versioning | — | ⚠️ Partial |
| `GetBucketCORS` | s3-protocol-compatibility | — | ✅ (cors.md reference) |
| `PutBucketCORS` | s3-protocol-compatibility | — | ✅ (cors.md reference) |
| `GetBucketLifecycle` | lifecycle-cost | — | ✅ Full |
| `PutBucketLifecycle` | lifecycle-cost | — | ✅ Full |
| `GetBucketReplication` | replication-versioning | — | ✅ Full |
| `PutBucketReplication` | replication-versioning | — | ⚠️ Partial |
| `GetObjectRetention` | replication-versioning | — | ✅ (object-lock.md) |
| `PutObjectRetention` | replication-versioning | — | ⚠️ Partial |
| `GetObjectLegalHold` | replication-versioning | — | ✅ (object-lock.md) |
| `PutObjectLegalHold` | replication-versioning | — | ⚠️ Partial |
| `GetPublicAccessBlock` | security-iam-policy | — | ⚠️ Partial |
| `PutPublicAccessBlock` | security-iam-policy | — | ⚠️ Partial |

## Coverage Summary

| Status | Count | Percent |
|--------|-------|---------|
| ✅ Full | 22 | 47% |
| ⚠️ Partial | 21 | 45% |
| ❌ Not Covered | 4 | 8% |
| **Total** | **47** | **100%** |

## Gap Analysis

### Not Covered (P1): Static Website, Torrent, Logging
These are less commonly diagnosed operations. Static website issues (404, routing) and bucket logging configuration failures are edge cases for most object storage users.

### Partial Coverage (P2): Write Operations
Most write operations (Put*, Delete*, Create*) have partial coverage because:
- Skills default to read-only diagnosis
- Write commands are tagged `manual-only`
- The main gap is in validating whether a write FAILED due to permissions vs configuration vs resource constraints

### Recommendations
1. Add `PutBucketEncryption` / `GetBucketEncryption` reference to security-iam-policy (ACE encryption configuration)
2. Add `ListParts` / `ListMultipartUploads` to s3-protocol-compatibility (multipart state diagnosis)
3. Add `RestoreObject` to lifecycle-cost (archive retrieval diagnosis)
4. Consider adding `GetBucketWebsite` / `PutBucketWebsite` to a future static-website skill
