# rclone Diagnostic Analysis

rclone is a widely-used tool for syncing files across storage providers including S3-compatible endpoints.

## Version Check
```bash
rclone version
```

## Key Configuration

### Remote Setup
```
[rclone-remote]
type = s3
provider = Other
env_auth = false
access_key_id = [REDACTED]
secret_access_key = [REDACTED]
endpoint = https://s3.example.com
region = us-east-1
location_constraint = us-east-1
acl = private
```

### Important rclone S3 Parameters
| Parameter | Default | Notes |
|---|---|---|
| `endpoint` | (required) | Must include protocol |
| `region` | us-east-1 | Required for SigV4 |
| `location_constraint` | (empty) | Required for bucket creation |
| `acl` | private | Can cause errors if provider doesn't support ACLs |
| `server_side_encryption` | (empty) | SSE-S3, SSE-KMS, SSE-C |
| `sse_kms_key_id` | (empty) | KMS key ARN |
| `storage_class` | STANDARD | Affects lifecycle |
| `upload_cutoff` | 200M | Above this, use multipart |
| `chunk_size` | 5M | Part size for multipart |
| `max_upload_parts` | 10000 | Max parts per multipart upload |
| `copy_cutoff` | 4.656G | Above this, must use multipart copy |
| `disable_checksum` | false | Skip MD5 checksum |
| `no_check_bucket` | false | Skip bucket existence check |
| `use_multipart_uploads` | true | Whether to use multipart for uploads |
| `use_multipart_etag` | true | Multi-part ETag checking |
| `use_presigned_request` | false | Use pre-signed URLs |
| `list_chunk` | 1000 | Page size for ListObjects |
| `list_version` | 2 | ListObjects version (1 or 2) |
| `no_head_object` | false | Avoid HeadObject if possible |
| `encoding` | Slash,InvalidUtf8 | Character encoding |

## Debug Output
```bash
rclone ls remote:bucket --dump headers --verbose --log-file rclone.log
rclone copy source dest --progress --dump headers -vv
```

Key sections:
- `--dump headers` — Shows request/response headers.
- `--dump bodies` — Shows request/response bodies (WARNING: may contain data).
- `-vv` — Very verbose, shows retries and decisions.

## Common rclone Issues

### 1. Corrupted on Transfer
**Symptom:** `corrupted on transfer: md5 hash differs` or `size differ`.

**Causes:**
- Multipart ETag validation failure (rclone computes full object hash, compares to ETag).
- S3-compatible provider returns ETag in different format.
- `use_multipart_etag = true` but provider's multipart ETag doesn't match rclone's expectation.
- SSE changes ETag semantics.

**Fix options:**
- `--ignore-checksum` — Skip checksum validation (risk of silent corruption).
- `--s3-use-multipart-etag=false` — Skip multipart ETag validation.
- `--checksum` — Use a different checksum algorithm if supported.

### 2. Size Diff After Copy
**Symptom:** Source and destination files have different sizes after copy.

**Causes:**
- `copy_cutoff` causing multipart copy with partial part.
- Source and destination use different chunk sizes.
- Content transformation by provider.
- Encoding transformation (gzip on the wire).

### 3. Directory Marker Objects
- S3 has no directories; rclone creates zero-byte objects with trailing `/` as markers.
- Listing with `--no-traverse` may miss or double-count markers.

### 4. Path vs Virtual-Hosted Style
- rclone uses path-style by default for non-AWS endpoints.
- Override: `force_path_style = false` for virtual-hosted.
- DNS must resolve for virtual-hosted style.

### 5. Retry Logic
- rclone retries on low-level errors up to `--low-level-retries` (default 10).
- Retries with backoff.
- Transient errors from S3-compatible providers may exhaust retries.

### 6. `list_version = 2` Issues
- Some providers don't support ListObjectsV2.
- Switch to `list_version = 1` for providers without V2 support.

### 7. HeadObject on Missing Objects
- rclone calls HeadObject to check object existence.
- Some providers return 404; others return 403 (AccessDenied) for nonexistent objects.
- rclone may misinterpret 403 as permission error.

## Configuration Print (Redacted)
```bash
rclone config show <remote>
# WARNING: Contains plaintext credentials — redact AK/SK
```
