# Multipart Consistency

## When to read
Use when large uploads appear incomplete, invisible, or checksum mismatched.

## Checks
- Confirm `CompleteMultipartUpload` succeeded.
- List incomplete multipart uploads.
- Compare part count, expected object size, and final object metadata.
- Distinguish interrupted upload cleanup from completed object visibility.
