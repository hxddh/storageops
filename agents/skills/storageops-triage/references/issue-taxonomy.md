# Issue Taxonomy

Each object storage issue maps to one primary category and optionally one subcategory.
This taxonomy is the routing table for the triage Skill.

## Top-Level Categories

### signature_auth
**Symptom patterns:**
- SignatureDoesNotMatch
- The request signature we calculated does not match
- InvalidSignature
- AccessDenied with signature-related message
- 403 with `Code: SignatureDoesNotMatch`

**Primary route:** `storageops-s3-protocol-compatibility`
**Secondary route:** `storageops-security-iam-policy` (if signature correct but permission denied)

### permission_access_denied
**Symptom patterns:**
- 403 AccessDenied (non-signature)
- 403 Forbidden
- access denied by bucket policy
- IAM policy denial
- ACL restriction
- KMS key access denial

**Primary route:** `storageops-security-iam-policy`

### s3_protocol_compatibility
**Symptom patterns:**
- XML parsing errors from S3 API
- Unsupported operation errors
- Unexpected header behavior
- Chunked transfer encoding issues
- Content-MD5 behavior difference
- Canonical request mismatch

**Primary route:** `storageops-s3-protocol-compatibility`

### cli_sdk_behavior
**Symptom patterns:**
- rclone corrupted on transfer
- s5cmd incorrect concurrency
- bcecmd debug output oddity
- awscli retry loop
- Tool-specific error messages
- SDK exception stack traces

**Primary route:** `storageops-cli-sdk-diagnosis`

### multipart_upload
**Symptom patterns:**
- MultipartUploadNotFound
- InvalidPart
- InvalidPartOrder
- Part upload timeout
- CompleteMultipartUpload failure
- Duplicate part ETags

**Primary route:** `storageops-s3-protocol-compatibility`
**Secondary route:** `storageops-cli-sdk-diagnosis` (tool-specific multipart config)

### list_objects
**Symptom patterns:**
- Truncated listing
- Missing objects in listing
- Incorrect NextContinuationToken / NextMarker
- Prefix/delimiter behavior difference
- CommonPrefixes structure difference

**Primary route:** `storageops-s3-protocol-compatibility`

### checksum_etag
**Symptom patterns:**
- ETag mismatch after upload
- Content-MD5 validation failure
- rclone size diff after copy
- Integrity check failure
- Multipart ETag format difference (non-MD5)

**Primary route:** `storageops-s3-protocol-compatibility`

### performance_throughput
**Symptom patterns:**
- Upload speed below expected bandwidth
- Download speed degradation
- Intermittent throughput drops
- Time-to-first-byte high
- Parallel vs sequential performance disparity

**Primary route:** `storageops-performance-diagnosis`

### small_file_metadata
**Symptom patterns:**
- Many small files upload slow
- Listing thousands of objects slow
- Metadata operations slow (HeadObject, stat)
- Directory listing latency
- Readdir performance (mount context)

**Primary route:** `storageops-performance-diagnosis`
**Secondary route:** `storageops-mount-filesystem-workspace` (mount context)

### mount_filesystem_workspace
**Symptom patterns:**
- Mount hang or disconnect
- FUSE I/O error
- Git operation slow on mounted filesystem
- Workspace startup delay (OpenClaw, IDE, etc.)
- node_modules / venv on mounted storage
- Stat storm / metadata amplification

**Primary route:** `storageops-mount-filesystem-workspace`

### network_endpoint_access
**Symptom patterns:**
- Endpoint unreachable
- DNS resolution failure
- TLS handshake timeout
- SSL certificate error
- Connection reset
- Host header mismatch
- Cross-cloud latency spikes
- Private endpoint unreachable

**Primary route:** `storageops-network-endpoint-access`

### security_iam_policy
**Symptom patterns:**
- AccessDenied for specific actions
- Bucket policy evaluation concern
- Cross-account access question
- STS session token expired
- KMS decrypt failure
- SSE configuration question
- Public access block inquiry

**Primary route:** `storageops-security-iam-policy`

### lifecycle_cost
**Symptom patterns:**
- Unexpected storage cost
- Lifecycle transition not working
- Archive retrieval cost question
- Storage class migration inquiry
- Minimum storage duration charge
- Request fee concern

**Primary route:** `storageops-lifecycle-cost`

### unknown_insufficient_evidence
**Triggered when:**
- No error message, log, or concrete symptom provided
- Input is purely "it doesn't work" with no details
- Evidence is contradictory and cannot be resolved
- The issue spans multiple categories without a clear primary

**Action:** Request specific evidence from required-evidence checklist.
