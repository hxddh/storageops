# Provider-Specific Quirks: COS (Tencent Cloud Object Storage)

## ETag Behavior

- **Single PUT:** Returns MD5 hash of object content wrapped in quotes (32 hex chars).
  Compatible with AWS S3.
- **Multipart Upload:** The completed object's ETag is **not** the MD5 of the
  object content (like AWS S3, it carries the `<hex>-N` shape with a trailing part
  count). The previous claim here — that COS returns "MD5 of the first part's MD5
  + last part's MD5" — was **unverified and unsupported by Tencent docs**, so it
  has been removed; do not rely on a specific computation. If you must verify
  integrity, capture a real COS ETag and compare, or use a native tool.
  (Verified: ETag is not the object MD5 — Tencent COS docs, 2026-06. Exact
  multipart computation not confirmed against vendor docs.)
- **Workaround:** Use `--ignore-checksum` or `disable_checksum = true` with
  non-native tools against COS, or use a native tool (e.g. coscmd).

## Tool Compatibility Matrix

| Tool | Native Support | Requires Config | Known Issues |
|------|---------------|-----------------|--------------|
| COSCMD | ✅ Native | `~/.cos.conf` | Best for COS |
| rclone | ✅ Native | Use `tencentcos` backend type | Most reliable cross-tool |
| s5cmd | ⚠️ Via S3 compat | `--endpoint-url` + SigV4 | ETag mismatch likely |
| awscli | ⚠️ Via S3 compat | `--endpoint-url` + SigV4 | ETag mismatch for multipart |
| obsutil | ❌ Not supported | N/A | OBS proprietary only |

## Signature (Auth) Behavior

- **Algorithm:** COS supports both COS-native signing and AWS SigV4
  (V2 compatibility mode available on older buckets).
- **Headers:** COS uses standard HTTP headers plus `x-cos-*` custom headers.
- **Compatibility with AWS SigV4:** COS can be configured to accept AWS
  SigV4 signatures. This is the recommended mode for cross-tool access.

## ListObjects Behavior

- Supports V1 ListObjects.
- V2 (`list-type=2`) may not be supported on all regions/versions.
- `max-keys` default: 1000.
- Pagination standard (NextMarker).
- **Multipart upload listing:** Listing in-progress multipart uploads
  may return results differently from AWS S3 in terms of sorting and truncation.

## Multipart Upload

- **Part size:** Minimum 1 MB, maximum 5 GB.
- **Max parts:** 10,000.
- **Initiate:** Returns `UploadId` in XML response.
- COS has specific rules for overlapping part ranges.

## Storage Classes

| Class | Description | Minimum Duration |
|-------|-------------|-----------------|
| STANDARD | Default, frequent access | None |
| STANDARD_IA | Infrequent access | 30 days |
| ARCHIVE | Archive, requires restore | 90 days |
| DEEP_ARCHIVE | Deep archive | 180 days |

## Endpoint Format

- Regional: `cos.<region>.myqcloud.com`
- Path-style and virtual-hosted-style both supported.
- Internal endpoints available within Tencent Cloud VPC.

## Known Issues with Cross-Tool Access

1. **Multipart ETag incompatibility:** COS multipart ETags are **not** the
   AWS computation (and the exact COS algorithm is **unverified** — do not assume a
   specific formula; verify against a real ETag). Tools that expect AWS-style
   multipart ETags (rclone, awscli, s5cmd) may report `corrupted on transfer`.
   Fix: use rclone's `tencentcos` backend or `--ignore-checksum`, or compare with
   an explicit checksum instead of the ETag.

2. **SigV4 region:** When using awscli against COS endpoints with SigV4,
   the `--region` parameter must match the COS region exactly.

3. **Content-Type persistence:** COS may modify or drop Content-Type headers
   during server-side copy operations.

4. **ACL compatibility:** COS uses a simplified ACL model. AWS ACL XML
   bodies may be rejected or silently modified.
