---
name: storageops-s3-protocol-compatibility
description: >
  Diagnose S3 protocol-level failures: SignatureDoesNotMatch, InvalidArgument,
  MalformedXML, NotImplemented, MissingContentLength, BadDigest. Covers
  signature version mismatches (v2/v4), header ordering, chunked encoding,
  query string auth, and provider-specific S3 API differences. Use when errors
  suggest protocol-level issues rather than application errors.
maturity: stable
mode: light_heavy
estimated_tokens: 1400
trigger_keywords:
  - SignatureDoesNotMatch
  - InvalidArgument
  - MalformedXML
  - NotImplemented
  - MissingContentLength
  - BadDigest
  - signature version
  - SigV2
  - SigV4
  - chunked encoding
  - query string auth
  - presigned URL
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# S3 Protocol Compatibility Diagnosis

Diagnose failures at the S3 wire protocol level. Most issues reduce to: signature mismatch, header encoding, XML body format, or missing API implementation.

## Decision Tree

```
Protocol error →
  ├─ SignatureDoesNotMatch? → Signature path
  │   ├─ SigV2 tool → SigV4-only endpoint? → Switch to SigV4 or enable SigV2 on endpoint
  │   ├─ SigV4 + StringToSign mismatch? → Clock skew, wrong region, or header reordering by proxy
  │   └─ Presigned URL expired? → Check Expires parameter, check clock
  ├─ MalformedXML? → XML body path
  │   ├─ Request body has wrong XML? → Check API doc for correct schema
  │   └─ Response body unparseable? → Provider returned non-standard XML
  ├─ NotImplemented? → Missing API
  │   ├─ S3 API not supported by provider? → Find alternative API or SDK
  │   └─ Feature gated (requires opt-in)? → Check provider docs
  ├─ InvalidArgument? → Parameter error
  │   ├─ Header value? → Check value format, encoding, valid range
  │   └─ Query parameter? → Check parameter name and value encoding
  └─ 400 Bad Request (no code)? → Debug-level header inspection needed
```

## Workflow

### Step 1: Extract Signature Information
From debug output: signature version (v2/v4), `StringToSign`, `CanonicalRequest`, and `Authorization` header format. See `references/signature-analysis.md`.

### Step 2: Compare Against AWS S3 Baseline
AWS S3 is the reference implementation. Check `references/aws-s3-api-reference.md` for expected behavior of the failing operation.

### Step 3: Identify Provider-Specific Quirks
See `references/provider-protocol-differences.md` for known differences per provider (BOS header naming, OSS signature region requirement, COS chunked encoding behavior).

### Step 4: Root Cause Classification
- **Tool-side**: wrong signature version, clock skew, header reordering by proxy/lib
- **Provider-side**: missing API, non-standard error format, stricter validation
- **Protocol mismatch**: chunked transfer encoding, Content-MD5 vs x-amz-content-sha256, virtual-hosted vs path-style

### Step 5: Scope
Is this a single-operation issue or a systemic compatibility problem? Test with a simple operation (ListBuckets) to isolate.

## Output Format

```markdown
# Diagnosis: [one-line]
**Root cause**: sigv2-vs-v4 | clock-skew | header-reordering | missing-api | xml-format | chunked-encoding | provider-quirk
**Confidence**: high | medium | low

## Evidence
- Error: [code + message]
- Signature version: [v2/v4, if known]
- Provider: [AWS/BOS/OSS/COS/GCS]
- Endpoint URL: [sanitized]

## Protocol Analysis
[StringToSign or CanonicalRequest analysis if available]

## Recommendations
1. **[fix]** (manual-only) — [config change or SDK upgrade]
2. **[workaround]** — [alternative API or SDK]
```

## Examples

### Example 1: SigV2 tool → SigV4-only BOS endpoint
**Input**: s3cmd (SigV2 default) against BOS endpoint. Error: `SignatureDoesNotMatch`.
**Diagnosis**: BOS requires SigV4 by default; s3cmd defaults to SigV2.  
**Fix**: `--signature-v2` flag on s3cmd (if BOS supports it), or switch to aws CLI/SDK which use SigV4.

### Example 2: Chunked encoding rejected
**Input**: SDK upload with `x-amz-content-sha256: STREAMING-AWS4-HMAC-SHA256-PAYLOAD`. Error: `InvalidArgument: Chunked transfer encoding not supported`.
**Diagnosis**: Provider doesn't support AWS chunked upload (aws-chunked).  
**Fix**: Set `Content-Length` header explicitly (single-shot upload), or use SDK flag to disable chunked encoding. Check `references/provider-protocol-differences.md`.

### Example 3: Virtual-hosted style DNS failure
**Input**: `https://bucket.s3.bj.bcebos.com/obj` → `NameResolutionError`.
**Diagnosis**: BOS doesn't support virtual-hosted style for custom endpoints. Must use path-style.  
**Fix**: Use `https://s3.bj.bcebos.com/bucket/obj` (path-style).

## References
- `references/signature-analysis.md` — SigV2 vs SigV4 deep dive, StringToSign format
- `references/aws-s3-api-reference.md` — AWS S3 baseline behavior by operation
- `references/provider-protocol-differences.md` — BOS/OSS/COS/GCS protocol quirks
- `references/header-reference.md` — Standard and provider-specific headers
- `references/chunked-encoding.md` — aws-chunked, content-length, transfer-encoding
- `references/url-styles.md` — Virtual-hosted vs path-style across providers
- `references/xml-format.md` — Request/response XML schemas and provider differences
- `references/error-codes.md` — Per-provider error code mapping
- `references/endpoint-construction.md` — Endpoint URL patterns per provider
- `references/character-encoding.md` — Unicode/encoding in keys and headers
