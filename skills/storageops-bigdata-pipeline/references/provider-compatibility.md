# Big Data Provider Compatibility

## When to read
Use for BOS, OSS, COS, OBS, MinIO, or other non-AWS S3-compatible endpoints.

## Checks
- Endpoint style: virtual-hosted vs path-style.
- Multipart behavior and ETag semantics.
- LIST delimiter/pagination quirks.
- SDK/S3A version compatibility with provider signing requirements.

## Routing
If errors are signature, XML, checksum, or endpoint style related, involve `storageops-s3-protocol-compatibility`.
