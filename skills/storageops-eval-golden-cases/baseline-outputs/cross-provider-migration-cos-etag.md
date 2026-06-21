# Summary

Category: migration_sync
Route: storageops-migration-sync
Confidence: 0.87
Root Cause Type: cross_provider_etag_mismatch_not_corruption
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=cross_provider_etag_mismatch_not_corruption, affected_layer=object-store

The migration is not corrupting data. Tencent COS does not compute multipart ETags
with the AWS algorithm, so for every multipart object the AWS source ETag and the
COS destination ETag differ even though the bytes are identical. The evidence is
decisive: `rclone check --size-only` reports 0 differences, and only single-part
objects (whose ETag is a plain MD5) verify clean — exactly the signature of a
cross-provider multipart ETag-format difference, not data loss.

# Key Evidence

- `--size-only` shows 0 differences, so every object is present at the correct byte
  size; the 412 "differences" come only from the hash/ETag comparison.
- Only multipart objects differ; single-part objects (plain-MD5 ETag) verify clean —
  the mismatch tracks the multipart ETag computation, not the data.
- The COS multipart ETag carries the same part count (`-14`) but a different hex
  digest, consistent with a different multipart algorithm rather than altered bytes.
- A multipart ETag is never the whole-object MD5, and COS's multipart computation is
  not AWS's, so cross-provider ETag equality cannot be expected.

# Remediation

- Verify this migration with an explicit content checksum (e.g. an enabled
  `x-amz-checksum-sha256` or a streamed full-object hash on a sample), not by
  comparing raw multipart ETags across providers; `rclone check --size-only` plus a
  sampled explicit-hash check is sufficient here.
- Make the verifier provider-aware: skip the ETag comparison for multipart objects on
  COS (see the cross-provider-compatibility reference) and compare on size + explicit
  checksum instead.
- Do not re-run the whole migration or delete the destination; the data is intact and
  only the multipart ETag format differs between AWS and COS.
