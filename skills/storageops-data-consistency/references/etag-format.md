# ETag Formats

## When to read
Use when users mention ETag mismatch, checksum mismatch, multipart upload, or encrypted objects.

## Patterns
- Plain single-part uploads often use MD5-like ETags.
- Multipart ETags often end with `-<part-count>` and are not the MD5 of the full object.
- SSE-KMS/SSE-C and provider-specific implementations may produce non-MD5 ETags.

For the authoritative per-provider ETag matrix (S3/MinIO/BOS/OSS/COS shapes,
computations, and verification status), see the canonical source:
`storageops-s3-protocol-compatibility/references/checksum-etag.md`. Do not restate
provider ETag algorithms here — link to that file to avoid drift.

## Tooling
Use `scripts/etag_parser.py` to classify samples when provided.
