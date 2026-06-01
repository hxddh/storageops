# storageops-s3-protocol-compatibility Scripts

## `parse_sigv4_error.py`

Parse a `SignatureDoesNotMatch` XML response or client debug log and extract:
- Error code/message
- StringToSign
- CanonicalRequest
- Credential scope (date, region, service)
- Signed headers, method, path, query, payload hash
- Conservative likely causes to inspect next

```bash
./parse_sigv4_error.py ../cases/signature-clock-skew/input/error-response.xml --json
./parse_sigv4_error.py awscli-debug.log
```

The parser is offline-only. It does not compute signatures, derive signing keys, or contact cloud endpoints.

## Planned Scripts

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
