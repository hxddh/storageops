# 摘要

Category: s3_protocol_compatibility
Route: storageops-s3-protocol-compatibility
Confidence: 0.82

`SignatureDoesNotMatch` is consistent with SigV4 clock skew: the request
timestamp differs from service UTC time enough to invalidate the signature.

# 诊断结论

The likely root cause is clock_skew, not a credential typo. SigV4 signs the
timestamp, CanonicalRequest, and credential scope together.

# 关键证据

- Error: SignatureDoesNotMatch.
- Evidence mentions clock skew and timestamp mismatch.
- SigV4 validation depends on UTC time and canonical request fields.

# 修复建议

Sync the host clock with NTP or chrony, confirm UTC time, then retry the request.
If it still fails, compare the CanonicalRequest and StringToSign.
