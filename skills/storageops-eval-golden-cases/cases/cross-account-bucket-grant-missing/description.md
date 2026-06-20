# Cross-account 403 — resource-side (bucket policy) grant missing

The mirror image of the classic cross-account denial. Here Alice's **IAM policy
already allows** `s3:GetObject`, but the bucket owner's policy (account B) only
names an in-account role and never grants account A or Alice. Cross-account
access is an AND of both sides, so the identity allow alone is not enough.

Expected diagnosis: blocked at the **bucket policy** (resource-based policy).
Remediation is to add a bucket-policy statement allowing `s3:GetObject` to the
caller principal (or its account root `arn:aws:iam::111111111111:root`). The
`cross_account_access_validator.py` helper reports `blocked_at: resource_policy`.
This is distinct from `access-denied-cross-account`, where the identity side was
the missing link.
