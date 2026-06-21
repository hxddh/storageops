# Summary

Category: s3_protocol_compatibility
Route: storageops-s3-protocol-compatibility
Confidence: 0.86
Root Cause Type: oss_sigv4_region_mismatch
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=oss_sigv4_region_mismatch, affected_layer=protocol

The credentials are valid; the SigV4 signing region is wrong for this endpoint. The
credential scope signs for `us-east-1`, but the Alibaba OSS endpoint
`oss-cn-hangzhou.aliyuncs.com` is region `cn-hangzhou`. OSS validates the region in
the SigV4 credential scope, so a signature computed for the wrong region is
rejected with SignatureDoesNotMatch even though the access key and secret are
correct — which is why the same client works against AWS S3 but fails here.

# Key Evidence

- The error is SignatureDoesNotMatch (a signing problem), not AccessDenied (a
  permission problem), so the key/secret are not the issue.
- CredentialScope is `.../us-east-1/s3/aws4_request` while the endpoint host
  `oss-cn-hangzhou.aliyuncs.com` is region cn-hangzhou — a region mismatch in the
  signature.
- A HEAD with the same credentials fails identically, consistent with every request
  being signed for the wrong region rather than an object-level permission issue.
- The access key/secret were verified in the OSS console, ruling out bad credentials.

# Remediation

- Set the SigV4 signing region to match the OSS endpoint region (cn-hangzhou),
  e.g. `AWS_REGION=cn-hangzhou` / `--region cn-hangzhou`, so the credential scope
  matches the endpoint.
- Prefer the provider's native endpoint/region configuration (or the OSS-native
  client) for OSS rather than AWS S3 defaults; see the OSS provider-quirks
  reference for the signing-region requirement.
- Do not rotate the access key or disable signature verification — the credentials
  are correct and the fix is the signing region.
