# Cross-Provider Compatibility

## When to read
Use when migrations cross AWS/BOS/OSS/COS/OBS/MinIO or metadata/ACL/checksum mismatches occur.

## Risks
- ETag is not always a full-object MD5.
- Metadata keys may be normalized or dropped.
- ACL and ownership models differ.
- Storage class and lifecycle semantics differ.

## Validation
Compare object count, total bytes, sampled metadata, and checksums where provider semantics allow.
