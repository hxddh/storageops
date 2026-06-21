# Summary

Category: consistency_integrity
Route: storageops-data-consistency
Confidence: 0.88
Root Cause Type: bos_multipart_etag_format
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=bos_multipart_etag_format, affected_layer=object-store

The object is not corrupted. Baidu BOS formats a multipart ETag as a leading-dash
`-<32 hex>` — the MD5 of the concatenated part MD5s, with no part count — whereas
AWS S3 and MinIO use a trailing `<hex>-N`. The verifier flags the object only
because it assumes the AWS ETag shape (and that the ETag equals the whole-object
MD5); neither holds for a BOS multipart object, so the mismatch is a format
difference, not data loss.

# Key Evidence

- The BOS ETag begins with a leading dash (`-3b1c...`), the BOS multipart format,
  not the AWS trailing `-N` and not a plain MD5.
- The byte count matches the local file exactly, and the same pipeline passes on
  AWS S3 and MinIO — consistent with a provider ETag-format difference, not corruption.
- A multipart ETag is the MD5 of the concatenated part MD5s, so it never equals the
  whole-object MD5 the verifier compares against.
- `multipart_etag_calculator.py --provider bos` reproduces the leading-dash ETag
  from the part MD5s, confirming the format.

# Remediation

- Treat the object as intact: verify integrity with an explicit content checksum
  (e.g. a streamed full-object MD5/SHA-256), not the ETag.
- Make the verifier provider-aware: recognise the BOS leading-dash ETag (and skip
  the AWS `-N` assumption) using `etag_parser.py`; compare BOS↔other providers on an
  explicit checksum, never on the raw multipart ETag.
- Do not delete or re-copy the object; the data is correct, only the ETag format
  differs across providers.
