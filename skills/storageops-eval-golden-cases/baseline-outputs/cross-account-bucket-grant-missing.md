# Summary

Category: security_iam_policy
Route: storageops-security-iam-policy
Confidence: 0.87
Root Cause Type: cross_account_missing_bucket_grant
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=cross_account_missing_bucket_grant, affected_layer=bucket-policy

This is a cross_account access denial blocked at the resource-based policy. Alice's
IAM policy in account 111111111111 already allows `s3:GetObject` on shared-data,
but the bucket policy on account 222222222222 only grants an in-account role and
never names account A or Alice. Cross-account access requires both the identity
policy AND the bucket policy to allow the action, so the resource-side gap blocks
the request.

# Key Evidence

- The error states "no resource-based policy allows the s3:GetObject action" —
  the denial is on the bucket policy, not the identity.
- Alice's IAM policy already allows `s3:GetObject` on `arn:aws:s3:::shared-data/*`,
  so the identity link of the cross_account chain is satisfied.
- The bucket policy's only statement names `arn:aws:iam::222222222222:role/internal-reader`;
  it grants no principal in account 111111111111.
- `cross_account_access_validator.py` reports `blocked_at: resource_policy` for
  principal `arn:aws:iam::111111111111:user/alice`.

# Remediation

- Add a bucket policy statement on account 222222222222 that sets Effect Allow,
  Action `s3:GetObject`, and a principal naming the caller — either Alice's user
  ARN or the account root `arn:aws:iam::111111111111:root` — scoped to
  `arn:aws:s3:::shared-data/*`.
- Keep the grant least-privilege: name the specific cross-account principal and
  bucket/prefix. Do not open the bucket to everyone and keep block-public-access on.
- Re-test with `aws s3 cp s3://shared-data/report.csv . --profile account-a` to
  confirm both the IAM allow and the new bucket policy allow now line up.
