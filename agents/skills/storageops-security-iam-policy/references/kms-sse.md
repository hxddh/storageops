# KMS and SSE

## SSE Types

### SSE-S3 (Server-Side Encryption with S3-Managed Keys)
- **Header:** `x-amz-server-side-encryption: AES256`
- **Key management:** Fully managed by S3.
- **Permission:** No KMS permissions needed.
- **ETag:** NOT the MD5 of plaintext.
- **Cost:** Minimal (included in S3 cost).

### SSE-KMS (Server-Side Encryption with KMS Keys)
- **Header:** `x-amz-server-side-encryption: aws:kms`
- **Header (key):** `x-amz-server-side-encryption-aws-kms-key-id: <key-arn>`
- **Key management:** AWS KMS customer-managed key (CMK).
- **Permission:** Requires `kms:Decrypt` and `kms:GenerateDataKey` on the KMS key.
- **ETag:** NOT the MD5.
- **Cost:** KMS API call cost per encrypt/decrypt operation.

### SSE-C (Server-Side Encryption with Customer-Provided Keys)
- **Headers:** `x-amz-server-side-encryption-customer-algorithm: AES256`, etc.
- **Key management:** Customer provides the encryption key with each request.
- **Permission:** No special permissions needed.
- **ETag:** IS the MD5 of the encrypted object.
- **Responsibility:** Customer must manage and protect the key.

### Dual-Layer (SSE-KMS + SSE-C)
- Not supported by AWS S3 but some providers may support.

## KMS Permission Model

### Required KMS Permissions for SSE-KMS

#### Upload (PutObject with SSE-KMS)
```
kms:GenerateDataKey  — on the KMS key.
```

#### Download (GetObject with SSE-KMS)
```
kms:Decrypt  — on the KMS key.
```

### KMS Key Policy
Separate from S3 bucket policy. The KMS key policy must allow:
- The IAM user/role to call `kms:GenerateDataKey` and `kms:Decrypt`.
- The S3 service to use the key (in some configurations).

## Common KMS/SSE Issues

### 1. KMS Access Denied
**Symptom:** S3 operation fails with `KMS.AccessDeniedException` or `403 AccessDenied (KMS)`.
**Cause:** The principal does not have `kms:Decrypt` or `kms:GenerateDataKey` on the KMS key.
**Check:** KMS key policy.

### 2. KMS Key Not Found / Disabled
**Symptom:** `KMS.NotFoundException` or `KMS.DisabledException`.
**Cause:** KMS key deleted, disabled, or in wrong region.
**Note:** Deleting a KMS key makes ALL objects encrypted with it unreadable FOREVER.

### 3. KMS Throttling
**Symptom:** Intermittent `KMS.ThrottlingException` or `KMS.RateExceededException`.
**Cause:** Too many KMS API calls per second. KMS has a per-second rate limit.
**Impact:** High-throughput GET/PUT with SSE-KMS can hit KMS rate limits.
**Mitigation:** Use SSE-S3 instead, or request KMS rate limit increase, or use bucket-level key.

### 4. Cross-Account KMS Access
**Symptom:** Account A tries to read Account B's SSE-KMS object, fails.
**Cause:** Account B's KMS key policy doesn't grant Account A access.
**Required:** Account B must add Account A's principal to both:
- S3 bucket policy (Allow GetObject).
- KMS key policy (Allow kms:Decrypt).

### 5. ETag Mismatch with SSE
**Symptom:** checksum verification fails for SSE-encrypted objects.
**Cause:** SSE-S3 and SSE-KMS ETags are NOT content MD5 hashes.
**Impact:** Tools expecting ETag = MD5 will falsely report corruption.
**Check:** `references/checksum-etag.md` in `storageops-s3-protocol-compatibility`.

## Encryption in Transit vs At Rest

- **In transit:** TLS (HTTPS) encrypts data on the wire.
- **At rest:** SSE encrypts data stored on disk.
- Both are recommended; TLS alone does not protect data at rest.

## SSE on S3-Compatibles

Not all S3-compatible providers support all SSE types:
- MinIO: Supports SSE-S3 and SSE-C.
- BOS: Supports proprietary encryption.
- OSS: Supports SSE-OSS (proprietary), SSE-KMS, SSE-C.
- COS: Supports SSE-COS (proprietary).
- Check provider-specific documentation.
