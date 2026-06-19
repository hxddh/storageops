# Summary

Category: consistency_integrity
Route: storageops-data-consistency
Confidence: 0.85
Root Cause Type: multipart_etag_not_md5

The object is almost certainly intact. The verification job compared a local MD5
against a multipart ETag, which is not an MD5 of the object bytes. The remote
ETag `"9f2a1d4e6a7b8c901122334455667788-17"` ends in `-17`, the multipart part
count — the hallmark of a multipart upload. This is a verification_method_error,
not corruption.

# Key Evidence

- The remote ETag carries a `-17` suffix, so it is a multipart ETag (MD5 of the
  concatenated part MD5s, then `-<part count>`), not a whole-object MD5.
- `size: 9134 MiB` with `aws s3 cp` at the default multipart threshold means the
  upload was split into parts, so the ETag cannot equal `local_md5`.
- The mismatch is structural: a multipart ETag will never match a single MD5,
  even for a perfectly stored object.

# Remediation

- Do not flag the object as corrupted on an ETag-vs-MD5 comparison alone.
- Verify integrity with a real checksum: re-upload (or copy) with
  `--checksum-algorithm SHA256` and compare the stored checksum metadata via a
  `HEAD` request (`aws s3api head-object` / `get-object-attributes`), which
  returns the provider-recorded checksum rather than the multipart ETag.
- Alternatively, recompute the expected multipart ETag using the same part size
  and compare against the stored ETag, or store your own MD5 as object metadata
  at upload time and read it back with `HEAD`.
