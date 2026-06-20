# Integrity Verification

## When to read
Use during or after a migration to prove the copy is complete and uncorrupted —
and to avoid the two classic false alarms: multipart-ETag mismatches read as
"corruption", and prefix-scoped counts that miss objects outside the sampled prefix.

## Mental model
"Verified" means two independent claims: **completeness** (every source object
exists at the destination) and **integrity** (each object's bytes are identical).
Counts and sizes prove completeness cheaply; only a content hash proves integrity,
and the ETag is a hash *only for single-part, unencrypted objects*.

## Checks (in order)
1. **Completeness by count and bytes, per prefix.** Compare object count and total
   bytes on each side for the same prefix. A mismatch localizes which prefix lost
   objects. Provider **inventory reports** (S3 Inventory, and provider equivalents)
   are the cheapest way to diff millions of keys without listing live.
2. **Integrity for single-part objects.** Their ETag = MD5(content), so equal ETags
   prove equal bytes. Equal size + equal ETag = verified.
3. **Integrity for multipart objects.** ETag = `MD5(concat(part MD5s))-N`, which
   depends on part size — different chunking gives a different ETag for identical
   bytes. **Do not flag this as corruption.** Confirm with
   `scripts/multipart_etag_calculator.py` (re-chunk vs corruption) and, where the
   provider supports it, use an explicit additional checksum instead of the ETag.
4. **Explicit checksums (strongest).** Enable `x-amz-checksum-sha256`/`-crc32c` on
   write so the destination stores a content checksum independent of part size;
   compare those. Tools: `aws s3 cp --checksum-algorithm SHA256`, rclone `--checksum`
   (compares hashes both sides), s5cmd size/mtime by default.
5. **Encrypted objects.** SSE-KMS/SSE-C rewrite the ETag, so ETag comparison is
   meaningless across an encryption boundary — rely on explicit checksums or a
   streamed full-object hash.

## How to confirm
```bash
# Count + bytes per side for a prefix:
aws s3 ls s3://<bucket>/<prefix> --recursive --summarize | tail -2
# Per-object integrity sample (single-part): compare ETag and size
aws s3api head-object --bucket <b> --key <k> --query '{etag:ETag,size:ContentLength,cksum:ChecksumSHA256}'
# Hash-level verify across a whole tree:
rclone check source:bucket/prefix dest:bucket/prefix --checksum
```

## Caveats / verification status
- ETag/checksum semantics are AWS-verified and hold for MinIO. BOS multipart ETag
  uses a leading-dash shape and OSS/COS multipart computations are not the AWS
  algorithm (see `../../storageops-s3-protocol-compatibility/references/checksum-etag.md`)
  — never compare multipart ETags across providers; use explicit checksums or a
  full-object streamed hash.
