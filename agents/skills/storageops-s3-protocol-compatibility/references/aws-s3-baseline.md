# AWS S3 Baseline Behavior

This document describes the expected behavior of AWS S3 for common operations.
Use this as a reference when comparing S3-compatible providers.

## Core Operations

### PutObject

- Creates or replaces an object.
- Returns ETag (MD5 of content, in quotes) for single PUT.
- Supports Content-MD5 header for integrity validation.
- Atomic: the object becomes available as a whole.
- Max single PUT size: 5 GB.

### GetObject

- Returns the object content with ETag and Content-Length.
- Supports Range header for partial reads.
- Can return metadata headers (x-amz-meta-*).
- Errors: NoSuchKey (404), AccessDenied (403).

### HeadObject

- Same metadata as GetObject without the body.
- Returns ETag, Content-Length, LastModified, Content-Type, metadata.
- Errors: 404 (NotFound), 403 (AccessDenied).

### DeleteObject

- Deletes a single object.
- Returns 204 No Content on success even if the object doesn't exist (idempotent).
- Versioned bucket: adds a delete marker; use `?versionId=` to permanently delete a version.

### CopyObject

- Creates a copy of an object within or between buckets.
- Server-side operation; data does not pass through the client.
- Source and destination buckets must be in the same region (with exceptions).
- Returns CopyObjectResult with ETag and LastModified.
- New ETag is generated; may differ from source.

### DeleteObjects (Multi-Object Delete)

- Deletes up to 1000 objects in one request.
- Returns list of deleted objects and any errors.
- Quiet mode returns only errors.

## List Operations

### ListObjects / ListObjectsV2

- See `list-objects.md` for detailed behavior.
- Max 1000 keys per response.
- Consistent pagination with IsTruncated flag.

### ListObjectVersions

- Lists all versions including delete markers.
- Same pagination model as ListObjects V1 (KeyMarker, NextKeyMarker, VersionIdMarker).

## Multipart Upload

- See `multipart-upload.md` for detailed lifecycle.
- Min part size: 5 MB (except last part).
- Max parts: 10,000.
- Max part size: 5 GB.
- UploadId TTL: indefinite until completed or aborted.

## Signature

- See `sigv4.md` for detailed signature process.
- All S3 operations use AWS Signature Version 4.
- Pre-signed URLs for time-limited access without credentials.

## Error Responses

All errors follow this XML structure:
```xml
<Error>
  <Code>ErrorCode</Code>
  <Message>Human-readable message</Message>
  <RequestId>request-id</RequestId>
  <HostId>host-id</HostId>
</Error>
```

Common error codes:
- `AccessDenied` — No permission.
- `NoSuchBucket` — Bucket doesn't exist.
- `NoSuchKey` — Object doesn't exist.
- `SignatureDoesNotMatch` — Auth failure.
- `RequestTimeTooSkewed` — Clock skew > 15 min.
- `InvalidAccessKeyId` — AKID not found.
- `SlowDown` — Request rate limit exceeded.
- `InternalError` — AWS internal error (retry).
- `ServiceUnavailable` — Temporary (retry).

## Compliance Notes for S3-Compatible Providers

When evaluating an S3-compatible provider against this baseline:

1. Not all error codes are implemented.
2. Not all operations are supported (e.g., some don't support CopyObject, Object Lock, versioning).
3. ETag semantics may differ.
4. Pagination may not behave identically (IsTruncated, MaxKeys enforcement).
5. Multipart part size/limit constraints may differ.
6. Signature validation may have subtle differences.
7. Header case sensitivity may vary.
8. XML namespace handling may differ.
