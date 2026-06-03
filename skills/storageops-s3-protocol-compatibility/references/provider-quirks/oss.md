# Provider-Specific Quirks: OSS (Alibaba Object Storage Service)

## ETag Behavior

- **Single PUT:** Returns MD5 hash of object content (32 hex chars, no suffix).
  Generally compatible with AWS S3. However, OSS may return ETags in a
  case-insensitive format in some regions.
- **Multipart Upload:** The completed object's ETag **differs from AWS S3** and
  is **not** the MD5 of the object content, so AWS-style multipart ETag
  verification (md5 of concatenated part md5s + `-N`) will fail — this can surface
  as rclone `corrupted on transfer`. Use the native `alibaba` backend or disable
  the AWS-style multipart-ETag check. (Verified that it differs from S3 / is not
  the object MD5 — Alibaba OSS docs, 2026-06. The exact OSS computation is **not**
  documented publicly; do not assume any specific algorithm — verify against a
  real ETag.)
- **CRC64:** OSS supports CRC64 checksums in addition to MD5. Use
  `x-oss-hash-crc64ecma` response header for integrity verification.

## Signature (Auth) Behavior

- **Algorithm:** OSS uses its own signing scheme, similar to but different
  from AWS SigV4. Uses `OSS` prefix instead of `AWS4`.
- **Header:** `Authorization: OSS <AccessKeyId>:<Signature>`.
- **Canonicalized headers:** `x-oss-*` headers are included in signing.
- **Compatibility:** rclone supports OSS natively (`type = alibaba` or `type = oss`).
  awscli may work with `--endpoint-url` if the signature difference is handled by the SDK.

## Tool Compatibility Matrix

| Tool | Native Support | Requires Config | Known Issues |
|------|---------------|-----------------|--------------|
| ossutil | ✅ Native | `~/.ossutilconfig` | Best for OSS |
| rclone | ✅ Native | Use `alibaba` backend type | Reliable, handles ETag quirks |
| s5cmd | ⚠️ Via S3 compat | `--endpoint-url` + SigV4 | Path-style only |
| awscli | ⚠️ Via S3 compat | `--endpoint-url` + SigV4 | SigV4 may not match OSS signing |
| bcecmd | ❌ Not supported | N/A | BOS proprietary only |

## ListObjects Behavior

- Supports V1 ListObjects only. **V2 (`list-type=2`) is NOT supported**
  on older OSS versions. Check OSS documentation for your region.
- `max-keys` default: 100.
- Pagination uses `NextMarker`.
- Prefix and delimiter work similarly to AWS S3.
- **rclone workaround:** Set `list_version = 1` in rclone config for OSS remotes.

## Multipart Upload

- **Part size:** Minimum 100 KB (much smaller than AWS S3's 5 MB minimum).
- **Max parts:** 10,000 per upload.
- **Initiate:** Returns `UploadId` in XML response body.
- **Abort:** Must explicitly abort incomplete uploads; OSS charges for
  stored incomplete parts.
- **Part numbering:** Must be sequential from 1.

## Server-Side Copy

- **CopyObject:** Available for objects up to 1 GB (smaller than AWS S3's 5 GB).
- **UploadPartCopy:** Available for larger objects via multipart copy.
- OSS charges for server-side copy operations within the same region.

## HeadObject on Non-Existent Objects

- Returns **404 Not Found** (compatible with AWS S3).

## Bucket Naming

- Must be globally unique across all OSS users.
- Lowercase letters, numbers, hyphens only.
- 3–63 characters.
- Cannot start/end with hyphen.

## Storage Classes

| Class | Description | Minimum Duration |
|-------|-------------|-----------------|
| STANDARD | Default, frequent access | None |
| IA | Infrequent access | 30 days |
| ARCHIVE | Archive (equivalent to Glacier) | 60 days |
| COLD_ARCHIVE | Deep archive | 180 days |

## Endpoint Format

- Regional endpoints: `oss-cn-hangzhou.aliyuncs.com` (external),
  `oss-cn-hangzhou-internal.aliyuncs.com` (internal/VPC).
- Both path-style and virtual-hosted-style are supported.
- **Path-style:** `https://<endpoint>/<bucket>/<key>` (default for non-AWS tools).
- **Virtual-hosted:** `https://<bucket>.<endpoint>/<key>`.

## Known Issues with Cross-Tool Access

1. **rclone multipart ETag mismatch:** OSS computes multipart ETags differently
   from AWS S3 (MD5 of part ETags vs MD5 of part MD5s). rclone may report
   `corrupted on transfer` even when data is intact. Fix: `--s3-use-multipart-etag=false`
   or use rclone's native `alibaba` backend.

2. **ListObjectsV2 not supported:** rclone defaults to `list_version = 2`.
   For OSS remotes, set `list_version = 1` to avoid failures.

3. **Part size minimum:** OSS allows 100 KB parts (vs AWS S3 5 MB). Tools
   configured with AWS defaults (5 MB) will work, but using smaller parts
   is possible for OSS-specific optimizations.

4. **ossutil against non-OSS endpoints:** ossutil's OSS-specific signing
   will fail against AWS S3 or other providers. Use s5cmd or rclone instead.

5. **Internal endpoint access:** Using `-internal` endpoints from outside
   Alibaba Cloud VPCs will fail with DNS/timeout errors. Check endpoint type.
