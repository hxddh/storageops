# Summary

Category: s3_protocol_compatibility
Route: storageops-s3-protocol-compatibility
Confidence: 0.88
Root Cause Type: multipart_etag_rechunk
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=multipart_etag_rechunk, affected_layer=protocol

The two multipart ETags differ because the object was re-chunked, not because the
data changed. A multipart ETag is the MD5 of the concatenated part MD5s followed
by `-<part count>`, so it depends on the part size. The source used 64 MiB parts
(2 parts → `-2`); rclone re-uploaded with 16 MiB parts (7 parts → `-7`). Different
part boundaries produce a different concatenation, hence a different ETag, even
though the bytes are identical.

# Key Evidence

- Both sides report the same size (104857600 bytes) and the streamed full-object
  MD5 matches, so the content is identical.
- Source ETag `...-2` vs destination ETag `...-7`: the trailing part count alone
  proves a different multipart part size was used (2 parts at 64 MiB vs 7 parts
  at 16 MiB).
- The multipart ETag is the MD5 of concatenated part MD5s, not the MD5 of the
  whole object, so it is sensitive to part size.
- `multipart_etag_calculator.py --total-size 104857600 --observed-etag <hex>-2`
  recovers the 64 MiB part-size band; `--other-part-size 16MiB` shows 7 parts and
  confirms the ETag necessarily differs.

# Remediation

- Treat the objects as equal: the verified full-object MD5 is the authoritative
  integrity check here, so suppress the migration tool's ETag comparison for
  multipart objects or compare on checksum instead.
- To make the destination ETag match the source, re-upload the object with the
  same multipart part size the source used (64 MiB), e.g. `rclone --s3-chunk-size 64M`.
- Going forward, pin a single part size across both sides so multipart ETags stay
  comparable. Do not delete or re-create the bucket; the data is correct.
