# Summary

Category: security_iam_policy
Route: storageops-security-iam-policy
Confidence: 0.86

Cross-account `s3:GetObject` fails because the bucket policy names principal
`111111111111`, but the caller still needs an IAM policy allow in that account.

# Key Evidence

- Evidence says cross_account access is attempted.
- Bucket policy and principal evidence are present.
- Missing IAM allow for `s3:GetObject` explains AccessDenied.

# Remediation

Add an IAM policy allow for `s3:GetObject` to the caller role or user, scoped to
the bucket/object ARN. Keep the bucket private and do not use `Principal:*`.
