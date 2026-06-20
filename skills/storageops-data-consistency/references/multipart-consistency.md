# Multipart Consistency

## When to read
Use when a large upload appears incomplete, invisible in listings, or its ETag
looks "wrong". The recurring theme: **an in-progress or never-completed multipart
upload is not an object yet**, and a multipart object's ETag is not the whole-object
MD5.

## Mental model
Multipart upload is three phases: `CreateMultipartUpload` → N × `UploadPart` →
`CompleteMultipartUpload`. The object becomes visible **only** after Complete
succeeds. Uploaded parts before Complete are real stored bytes (and may be billed)
but do not appear in `ListObjects` and cannot be read as the object. So "I uploaded
10 GB but the object isn't there" is almost always Complete never ran (client crash,
timeout, or an error swallowed by the SDK).

## Checks (in order)
1. **Did `CompleteMultipartUpload` succeed?** Look for its 200 in client logs. A
   `CompleteMultipartUpload` that returns 200 with an `<Error>` body in the payload
   is a *failure* — some SDKs mis-handle this.
2. **List incomplete uploads.** `aws s3api list-multipart-uploads --bucket <b>`
   shows orphaned uploads. If the key is here but not in `ListObjects`, Complete
   never ran → call Complete (if you still hold the parts/UploadId) or Abort.
3. **Part count and sizes.** Every part except the last must be ≥ 5 MiB (provider
   minimum); a too-small middle part makes Complete fail with `EntityTooSmall`.
   Parts must be contiguous part-numbers with the ETags returned by each UploadPart.
4. **ETag is not the object MD5.** A multipart ETag is `MD5(concat(part MD5s))-N`.
   A "checksum mismatch" against a whole-file MD5 is expected, not corruption —
   confirm with `scripts/multipart_etag_calculator.py` and see `etag-format.md`.
5. **Clean up to stop silent cost.** Add a lifecycle rule to abort incomplete
   multipart uploads after N days; orphaned parts otherwise accumulate invisibly.

## How to confirm
```bash
aws s3api list-multipart-uploads --bucket <bucket>
aws s3api list-parts --bucket <bucket> --key <key> --upload-id <id>
aws s3api head-object  --bucket <bucket> --key <key>   # exists only after Complete
```

## Caveats / verification status
- Phase semantics and the 5 MiB minimum-part rule are AWS-verified and hold for
  MinIO; BOS/OSS/COS honor the same multipart lifecycle but differ on ETag shape
  (see `etag-format.md`) and on exact minimum-part sizing — verify before asserting.
