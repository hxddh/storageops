# Cross-Provider Compatibility

## When to read
Use when a migration or sync crosses providers (AWS S3 ↔ Baidu BOS / Alibaba OSS /
Tencent COS / Huawei OBS / MinIO / GCS), or when post-migration verification reports
metadata, ACL, or checksum mismatches. The wire protocol is S3-compatible, but the
semantics underneath are not identical — most "corruption after migration" reports
are a semantic difference, not data loss.

> **Verify before asserting.** Provider behaviours and header names change by
> region/edition over time. Treat the notes below as orientation and confirm
> against the provider's current docs before concluding.

## The four things that differ (and how to handle each)

### 1. ETag / checksum semantics — the #1 false alarm
A multipart ETag is **not** a whole-object MD5, and the multipart computation is
provider-specific:
- AWS S3 / MinIO: `MD5(concat(part MD5s))-N` (trailing part count).
- Baidu BOS: same underlying hash but a **leading dash** `-<32 hex>`, no count.
- Alibaba OSS / Tencent COS: **not** the AWS computation; treat the exact algorithm
  as unverified.

So comparing multipart ETags **across providers is meaningless**. Verify integrity
with an explicit content checksum instead (e.g. `x-amz-checksum-sha256` where
supported, or a streamed full-object hash). See
`../../storageops-s3-protocol-compatibility/references/checksum-etag.md` for the
canonical matrix, and use
`../../storageops-data-consistency/scripts/multipart_etag_calculator.py` to confirm
a re-chunk vs corruption.

### 2. Metadata / header normalization
User metadata and system headers may be renamed or dropped across the boundary:
- AWS uses `x-amz-meta-*`; BOS uses `x-bce-meta-*`, OSS `x-oss-meta-*`, COS
  `x-cos-meta-*`. A naive copy that forwards `x-amz-*` headers verbatim may lose
  metadata at a non-AWS destination.
- Header **case** and ordering can be normalized; some providers lowercase keys.
- Content-Type / Content-Encoding usually carry over; custom headers may not.
Verify by sampling `HEAD` on both sides and diffing the user-metadata set.

### 3. ACL / ownership model
Canned ACLs (`private`, `public-read`) are broadly portable, but bucket-owner
enforcement, object ownership, and public-access toggles differ by provider. A
migrated object may land with a different effective owner/ACL — re-apply the intended
ACL explicitly at the destination rather than assuming it transferred.

### 4. Storage class & lifecycle
Class names and minimum-duration / minimum-billable rules differ (e.g. AWS IA/Glacier
vs OSS IA/Archive vs COS STANDARD_IA/ARCHIVE). A migration that preserves the source
class name may not map to an equivalent destination class — map classes explicitly.

## Verification method (provider-safe)
1. **Completeness:** compare object count and total bytes per prefix on each side
   (provider inventory reports where available).
2. **Integrity:** compare an **explicit checksum** (not the ETag) for sampled
   objects; for multipart objects never compare raw ETags across providers.
3. **Metadata/ACL:** `HEAD`-sample both sides and diff user metadata and effective
   ACL.
4. Treat a multipart-ETag-only mismatch as **expected** until an explicit checksum
   disagrees. See `integrity-verification.md` for the full procedure.

## Do not
- Conclude "corruption" from a cross-provider ETag mismatch alone.
- Assume `x-amz-*` metadata survives a copy to a non-AWS provider.
- Assume storage-class names or lifecycle minimums map one-to-one.
