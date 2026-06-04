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

## `check_payload_hash.py`

Optional offline falsifier for `BadDigest` / `BadDigestSHA256`. Given the
original (pre-encoding) object bytes and the declared `x-amz-content-sha256`,
report whether the declared hash was computed over the raw bytes while an encoded
body (e.g. gzip) was sent — the most common BadDigest cause.

```bash
./check_payload_hash.py --raw-file out.json \
  --declared-sha256 <x-amz-content-sha256 value> --content-encoding gzip --json
# Provide --sent-file <body.gz> for a byte-exact match when the sent body is captured.
```

Offline-only: computes SHA-256 of local files, never signs, never contacts an
endpoint. It confirms or refutes the mechanism; it does not route.

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
