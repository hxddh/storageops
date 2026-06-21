# Routing
Category: s3_protocol_compatibility
Route: storageops-s3-protocol-compatibility
Confidence: 0.80
Root Cause Type: signature_auth

A 403 carrying SignatureDoesNotMatch is a signature problem, not a permission denial,
so this routes to s3-protocol-compatibility (compare the canonical request, signing
region, and endpoint) rather than to security/IAM.

# Evidence Gaps
- Need the full debug trace: the client CanonicalRequest/StringToSign, the signing
  region and endpoint, and the SDK/tool version, to confirm the signature mismatch.
