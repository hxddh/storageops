# Multipart Upload Lifecycle

## Standard Lifecycle

```
1. CreateMultipartUpload
   POST /<bucket>/<key>?uploads
   → UploadId

2. UploadPart (1..N)
   PUT /<bucket>/<key>?partNumber=N&uploadId=<UploadId>
   → ETag for each part

3. CompleteMultipartUpload
   POST /<bucket>/<key>?uploadId=<UploadId>
   Body: <CompleteMultipartUpload>
           <Part><PartNumber>1</PartNumber><ETag>"etag1"</ETag></Part>
           ...
         </CompleteMultipartUpload>
   → Final ETag (multipart format)

4. (Optional) AbortMultipartUpload
   DELETE /<bucket>/<key>?uploadId=<UploadId>

5. (Optional) ListParts
   GET /<bucket>/<key>?uploadId=<UploadId>

6. (Optional) ListMultipartUploads
   GET /?uploads
```

## Part Number Rules

- Part numbers: 1 to 10,000.
- Must be unique within an upload.
- Order in CompleteMultipartUpload XML defines final object byte order.
- AWS S3 allows any order in the XML; some compatible providers require ascending order.

## ETag in CompleteMultipartUpload

- The ETag in CompleteMultipartUpload must match the ETag returned by UploadPart.
- Some providers return the ETag without quotes; others with quotes.
- The CompleteMultipartUpload XML should include the ETag exactly as received.
- AWS S3 requires ETags to match exactly (case-sensitive).

## Common Failure Scenarios

### InvalidPart
**Symptom:** One or more parts listed in CompleteMultipartUpload were not found.
**Causes:**
- Part ETag doesn't match what the server has.
- Part was uploaded to a different UploadId.
- Part was already completed or aborted.

### InvalidPartOrder
**Symptom:** Parts are not in the expected order.
**Causes:**
- Provider requires ascending part numbers in CompleteMultipartUpload XML.
- Part numbers overlap.

### CompleteMultipartUpload Timeout/Retry
**Symptom:** Client times out waiting for CompleteMultipartUpload response, retries.
**Causes:**
- Server is assembling parts (large object = slow).
- Network timeout during assembly.
- **Critical:** Double completing may create the object twice (different version IDs) or fail with NoSuchUpload.

### MultipartUploadNotFound
**Symptom:** UploadId referenced in UploadPart or CompleteMultipartUpload does not exist.
**Causes:**
- UploadId expired (provider-specific TTL, typically 24h–7d).
- UploadId was aborted.
- UploadId from wrong region.

### Orphaned Multipart Uploads
- Uncompleted uploads consume storage and incur charges.
- ListMultipartUploads to find orphans.
- AbortMultipartUpload to clean up (manual-only: destructive).

## Provider-Specific Differences

- **Min part size:** AWS S3 requires 5 MB (except last part). Some providers allow smaller.
- **Max parts:** AWS S3 allows 10,000. Some providers limit to 1,000.
- **Part size limit:** AWS S3 max 5 GB per part. Some vary.
- **UploadId TTL:** Varies from hours to days.
- **Abort behavior:** Some providers take time to reclaim space.
