# storageops-s3-protocol-compatibility Scripts

Future scripts for this domain (not yet implemented in v0.1):

## Planned Scripts

### `parse_sigv4_error.py`
Parse a SignatureDoesNotMatch XML response and extract:
- StringToSign
- CanonicalRequest  
- Expected vs actual signing components

Compare against client-computed values from debug log.

### `validate_multipart_lifecycle.py`
Given a debug log, trace a multipart upload through:
- CreateMultipartUpload
- UploadPart(s)
- CompleteMultipartUpload (or AbortMultipartUpload)

Report:
- Part count, size distribution
- Retried parts
- Missing/duplicated ETags
- Time between steps

### `compare_list_objects.py`
Given two ListObjects responses (e.g., provider vs AWS S3 expected), diff:
- Key ordering
- CommonPrefixes structure
- Pagination token format
- KeyCount accuracy

## Principles

- All scripts must operate on offline log files only.
- No network calls to real cloud endpoints.
- Output must be structured for downstream parsing.
- Secrets in input must be redacted before processing.
