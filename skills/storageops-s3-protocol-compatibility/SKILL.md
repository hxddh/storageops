---
name: storageops-s3-protocol-compatibility
description: >
  Diagnose S3 protocol-level failures: SignatureDoesNotMatch, InvalidArgument,
  MalformedXML, NotImplemented, MissingContentLength, BadDigest. Covers
  signature version mismatches (v2/v4), header ordering, chunked encoding,
  query string auth, and provider-specific S3 API differences. Use when errors
  suggest protocol-level issues rather than application errors.
maturity: core
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
From debug output: signature version (v2/v4), `StringToSign`, `CanonicalRequest`, and `Authorization` header format. See `references/sigv4.md`.

### Step 2: Compare Against AWS S3 Baseline
AWS S3 is the reference implementation. Check `references/aws-s3-baseline.md` for expected behavior of the failing operation.

### Step 3: Identify Provider-Specific Quirks
See `references/provider-quirks/bos.md` for known differences per provider (BOS header naming, OSS signature region requirement, COS chunked encoding behavior).

### Step 4: Root Cause Classification
- **Tool-side**: wrong signature version, clock skew, header reordering by proxy/lib
- **Provider-side**: missing API, non-standard error format, stricter validation
- **Protocol mismatch**: chunked transfer encoding, Content-MD5 vs x-amz-content-sha256, virtual-hosted vs path-style

### Step 5: Scope
Is this a single-operation issue or a systemic compatibility problem? Test with a simple operation (ListBuckets) to isolate.

### Step 6: Feedback Loop
If the root cause is unclear after scope analysis, ask the user: **"Can you provide the debug output with signature headers (`--debug` flag in aws CLI, `-vv --dump headers` in rclone)?"** For `SignatureDoesNotMatch`, compare the `StringToSign` and `CanonicalRequest` from debug output against the expected format in `references/sigv4.md`. If confidence < medium, go back to Step 2 and request a complete debug trace with the full authorization header (redact credentials).

## User Interaction

### When to ask the user:
- **"Can you share the debug output with full request/response headers?"** — protocol issues live in the headers
- **"What tool and version are you using? Does it use SigV2 or SigV4?"** — signature version mismatch is the #1 protocol issue
- **"What endpoint URL are you using (virtual-hosted style or path-style)?"** — DNS and URL format affect signing

### When to inform the user:
- Before suggesting a provider-side fix: **"This is the expected behavior of this provider's S3 implementation. Here's how to work around it."**
- After diagnosis: **"If the issue is a provider bug, please open a support ticket with the provider and reference the debug trace."**

## Output Format — ALWAYS use this exact template

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
**Fix**: Set `Content-Length` header explicitly (single-shot upload), or use SDK flag to disable chunked encoding. Check `references/provider-quirks/bos.md`.

### Example 3: Virtual-hosted style DNS failure
**Input**: `https://bucket.s3.bj.bcebos.com/obj` → `NameResolutionError`.
**Diagnosis**: BOS doesn't support virtual-hosted style for custom endpoints. Must use path-style.  
**Fix**: Use `https://s3.bj.bcebos.com/bucket/obj` (path-style).

## References
- `references/sigv4.md` — SigV2 vs SigV4 deep dive, StringToSign format | **Read when:** user reports SignatureDoesNotMatch or signature-related errors
- `references/aws-s3-baseline.md` — AWS S3 baseline behavior by operation | **Read when:** comparing provider behavior against AWS S3 reference
- `references/provider-quirks/bos.md` — BOS/OSS/COS/GCS protocol quirks | **Read when:** user mentions a non-AWS provider (BOS/OSS/COS/GCS)
- `references/sigv4.md` — Standard and provider-specific headers | **Read when:** debugging header ordering or specific header issues
- `references/multipart-upload.md` — aws-chunked, content-length, transfer-encoding | **Read when:** user reports InvalidArgument or chunked encoding errors
- `references/aws-s3-baseline.md` — Virtual-hosted vs path-style across providers | **Read when:** user reports DNS errors, NameResolutionError, or endpoint construction issues
- `references/list-objects.md` — Request/response XML schemas and provider differences | **Read when:** user reports MalformedXML or XML parsing errors
- `references/aws-s3-baseline.md` — Per-provider error code mapping | **Read when:** error code is unfamiliar or provider-specific
- `references/aws-s3-baseline.md` — Endpoint URL patterns per provider | **Read when:** user is constructing endpoint URLs or troubleshooting connectivity
- `references/list-objects.md` — Unicode/encoding in keys and headers | **Read when:** user reports encoding issues with special characters in object keys
