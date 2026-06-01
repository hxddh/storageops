# Provider-Specific Quirks: BOS (Baidu Object Storage)

## ETag Behavior

- **Single PUT:** Returns MD5 hash of object content (32 hex chars, no suffix).
  Compatible with AWS S3.
- **Multipart Upload:** Returns MD5 of concatenated part MD5s + `-N` suffix.
  However, BOS may compute the MD5 differently from AWS S3 in edge cases.

## Signature (Auth) Behavior

- **Algorithm:** BOS uses a proprietary authorization scheme, not standard AWS SigV4.
- **Header:** Uses `x-bce-*` custom headers extensively:
  - `x-bce-date` — Request timestamp (alternative to `Date`/`x-amz-date`).
  - `x-bce-content-sha256` — Content hash (similar to `x-amz-content-sha256`).
  - `x-bce-request-id` — Response tracking ID.
- **Compatibility:** awscli can be configured to work with BOS via `--endpoint-url`,
  but the signature format may differ. rclone has native BOS backend support
  (`type = bcebos` is preferred over `type = s3` for BOS).

## Tool Compatibility Matrix

| Tool | Native Support | Requires Config | Known Issues |
|------|---------------|-----------------|--------------|
| bcecmd | ✅ Native | `~/.bce/credentials` | Best for BOS |
| rclone | ✅ Native | Use `bcebos` backend type | Most reliable cross-tool |
| s5cmd | ⚠️ Via S3 compat | `--endpoint-url` + SigV4 | Path-style only |
| awscli | ⚠️ Via S3 compat | `--endpoint-url` + `--region` | Use signed requests; do not bypass authentication |
| obsutil | ❌ Not supported | N/A | OBS proprietary only |

## ListObjects Behavior

- Supports both V1 and V2 ListObjects.
- `max-keys` default: 1000.
- Pagination uses `NextMarker` (V1) and `NextContinuationToken` (V2).
- V2 `start-after` parameter may behave differently from AWS S3.

## Multipart Upload

- **Part size:** Minimum 5 MB (same as AWS S3).
- **Max parts:** 10,000 per upload.
- **Abort incomplete:** Supported via lifecycle rules.
- **Initiate:** `POST ?uploads` — BOS adds `x-bce-*` headers to the response.

## Server-Side Copy

- **CopyObject:** Supported for objects up to 5 GB.
- **CopyPart (Multipart Copy):** Supported for objects > 5 GB.
- BOS may internally convert server-side copies to multipart operations,
  causing ETag format changes (single PUT ETag → multipart ETag with `-N` suffix).

## HeadObject on Non-Existent Objects

- Returns **404 Not Found** (not 403 AccessDenied).
- Compatible with AWS S3 behavior.

## Bucket Naming

- Bucket names must be globally unique (similar to AWS S3).
- Only lowercase letters, numbers, and hyphens.
- Must be 3–63 characters.

## Storage Classes

| Class | Description | Minimum Duration |
|-------|-------------|-----------------|
| STANDARD | Default, frequent access | None |
| STANDARD_IA | Infrequent access | 30 days |
| COLD | Cold storage | 90 days |
| ARCHIVE | Archive storage | 180 days |

## Known Issues with Cross-Tool Access

1. **rclone server-side copy ETag mismatch:** When rclone does server-side copy
   between two BOS buckets, BOS may internally use multipart copy, changing
   the ETag format. This triggers rclone's `corrupted on transfer: md5 hash differ`.

2. **awscli path-style default:** awscli defaults to path-style for custom
   endpoints. BOS supports path-style but the Host header must match the endpoint
   exactly without the bucket name embedded.

3. **s5cmd Content-Type header:** s5cmd may send Content-Type headers that
   BOS rejects or silently ignores.

4. **Chunked transfer encoding:** Some versions of BOS reject chunked transfer
   encoding for PUT requests. boto3 streaming uploads may fail.
