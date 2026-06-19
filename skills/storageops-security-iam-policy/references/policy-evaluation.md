# Policy Evaluation

How S3 decides whether a request is allowed. AccessDenied can be produced at any
layer; the goal of diagnosis is to localize which one.

## Evaluation Order

For a request to succeed, it must survive every layer below. The request fails at
the FIRST layer that denies it.

```
Request →
  1. Explicit Deny (any policy: IAM, bucket, SCP, session, VPC endpoint)
  2. SCP / Organization policy (must allow)
  3. Identity (IAM) policy on the caller (must allow)
  4. Resource (bucket) policy (must allow for cross-account; can deny same-account)
  5. Session / permissions-boundary policy (must allow if present)
  6. ACL (legacy; bucket/object owner grants)
  7. Block Public Access (overrides public grants)
  8. Service-specific: KMS key policy, VPC endpoint policy
→ Allowed only if no Deny AND at least one Allow applies
```

## The Three Decisions

1. **Explicit Deny** anywhere → request denied. Nothing can override it.
2. **Explicit Allow** → required to pass. Same-account: an Allow in EITHER the IAM
   policy or the bucket policy is enough. Cross-account: BOTH the caller's IAM
   policy AND the bucket policy must allow.
3. **Implicit (default) Deny** → if no statement allows the action, it is denied.
   Most "no policy allows" errors are this case.

So the precedence is: **explicit deny > explicit allow > implicit deny**.

## How AccessDenied Arises Per Layer

- **SCP**: organization restricts the action. Error often says "explicit deny in
  a service control policy". Not visible to the bucket owner; ask the org admin.
- **IAM policy**: caller has no Allow, or has an explicit Deny, or a `Condition`
  (IP, VPC, MFA, tags) does not match.
- **Bucket policy**: cross-account caller not granted, or an explicit Deny (e.g.
  "deny unless aws:SourceVpce = ...", "deny unless SecureTransport").
- **Permissions boundary / session policy**: assumed-role session was issued with
  an inline policy narrower than the role; the boundary did not grant the action.
- **ACL**: object owned by another account, bucket ACL `private`.
- **Block Public Access**: a public grant is ignored even though the policy allows.
- **KMS**: object is SSE-KMS and the caller lacks `kms:Decrypt`/`kms:GenerateDataKey`.
- **VPC endpoint policy**: endpoint policy does not allow the bucket/action.

## Localizing the Failing Layer

Collect first: principal ARN, action, resource ARN, error code, request ID.

1. **Read the error text.** "explicit deny" → layer 1 (find the Deny). "explicit
   deny in a service control policy" → SCP. "is not authorized to perform" with no
   deny wording → usually missing Allow (IAM or bucket).
2. **Same-account vs cross-account.** Compare the account in the principal ARN to
   the account that owns the bucket. Cross-account requires both sides — check the
   bucket policy explicitly.
3. **Use the simulator (read-only).**
   ```
   aws iam simulate-principal-policy \
     --policy-source-arn <principal-arn> \
     --action-names s3:GetObject \
     --resource-arns arn:aws:s3:::bucket/key
   ```
   This evaluates IAM + attached SCPs/boundaries but NOT the bucket policy.
4. **Inspect the bucket policy directly.**
   ```
   aws s3api get-bucket-policy --bucket <bucket> --query Policy --output text
   aws s3api get-public-access-block --bucket <bucket>
   ```
5. **If the object is encrypted**, check `x-amz-server-side-encryption` on a
   `head-object` and move to `references/kms-permissions.md`.

## Evidence To Record

Principal ARN, action, resource ARN, error code + message excerpt, request ID, the
relevant Deny/Allow statement, and which layer you concluded blocked the request.
Note any `Condition` that did not match — these are the most common silent denials.
