# Cross-provider migration: COS multipart ETag differs from AWS

A non-AWS migration case. Copying multipart objects from AWS S3 to Tencent COS, the
post-migration hash check flags every multipart object because COS does not compute
multipart ETags with the AWS algorithm — only single-part objects (whose ETag is a
plain MD5) verify clean. The bytes are identical (`--size-only` shows 0 diffs).

Expected diagnosis (migration-sync): not corruption — a cross-provider multipart
ETag-format difference. Verify a cross-provider migration with an explicit content
checksum (or size + a provider-native integrity signal), never by comparing raw
multipart ETags across providers. This case keeps the migration corpus covering a
non-AWS destination, and exercises the cross-provider-compatibility reference.
