# Summary
Category: security_iam_policy
Route: storageops-security-iam-policy
Confidence: 0.86
Root Cause Type: kms_explicit_deny
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=kms_explicit_deny, affected_layer=kms

The 403 AccessDenied is a KMS authorization failure, not an S3 one: the caller is
denied kms:GenerateDataKey on the SSE-KMS key, so the PUT cannot encrypt.

# Key Evidence
- AccessDenied references kms:GenerateDataKey and a 403, i.e. the KMS key policy
  Deny (or missing allow) blocks the data-key request (the CallerAccount, e.g. 987654321098, is not granted).
- The S3 action itself is permitted; the failure is on the KMS key for SSE-KMS.

# Remediation
- Grant the caller kms:GenerateDataKey (and kms:Decrypt for reads) on the key in the
  KMS key policy; for cross-account, allow the principal and confirm no explicit Deny.
- Keep the bucket private; do not weaken encryption to work around the key policy.
