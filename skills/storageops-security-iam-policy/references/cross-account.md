# Cross-Account Access

Cross-account is the most common source of "IAM looks correct but still 403".
Cross-account access to S3 requires grants on **both** sides, and object ownership
adds a third trap.

## The Two-Sided Rule

For account A to access a bucket in account B, BOTH must be true:

1. **Caller side (account A)**: the IAM user/role must have an Allow for the S3
   action on the bucket/object ARN.
2. **Resource side (account B)**: the bucket policy must grant the account-A
   principal (or `arn:aws:iam::A:root`) the same action.

If either side is missing, the result is AccessDenied. Same-account access only
needs one side; cross-account needs both. This is why a policy that "works for our
own users" fails for an external account.

```json
// Bucket policy in account B
{
  "Effect": "Allow",
  "Principal": {"AWS": "arn:aws:iam::AAAAAAAAAAAA:role/app"},
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": ["arn:aws:s3:::bucket-b", "arn:aws:s3:::bucket-b/*"]
}
```
Note: `ListBucket` needs the bucket ARN; `GetObject` needs the `/*` object ARN.

## Role Assumption (sts:AssumeRole)

Instead of granting an external principal directly, account B can publish a role
that account A assumes:

1. Role in B has a **trust policy** allowing `sts:AssumeRole` from the A principal.
2. The A principal has IAM permission to call `sts:AssumeRole` on that role ARN.
3. After assuming, the caller acts AS a B principal, so the bucket policy may not
   even need a cross-account grant.

A broken trust policy (wrong account, missing `ExternalId`, condition mismatch)
surfaces as `AccessDenied` on the `AssumeRole` call itself, not on S3.

```
aws sts assume-role --role-arn arn:aws:iam::B:role/cross --role-session-name diag
```

## Object Ownership / ACL Pitfalls

When account A writes an object into B's bucket, by default A may **own** that
object. B's IAM users then get AccessDenied reading their own bucket's objects.

- **BucketOwnerEnforced** (Object Ownership setting): disables ACLs entirely and
  makes the bucket owner own all objects. This is the modern fix and what AWS
  recommends. After enabling it, ACL-based cross-account grants stop working.
- Older buckets may rely on the writer setting
  `--acl bucket-owner-full-control` on every PUT. If a writer omits it, the
  object stays owned by the writer and B cannot read it.

Check ownership and ACL settings:
```
aws s3api get-bucket-ownership-controls --bucket <bucket>
aws s3api get-object-acl --bucket <bucket> --key <key>
```

## Common AccessDenied Causes — and How To Verify

| Cause | Verify (read-only) |
|---|---|
| Bucket policy missing the A principal | `aws s3api get-bucket-policy --bucket <b>` |
| Caller IAM missing the action | `aws iam simulate-principal-policy ...` |
| Object owned by writer, not bucket owner | `aws s3api get-object-acl --bucket <b> --key <k>` |
| ACLs disabled (BucketOwnerEnforced) but grant relies on ACL | `aws s3api get-bucket-ownership-controls --bucket <b>` |
| SSE-KMS key not shared cross-account | `aws s3api head-object` → see `references/kms-permissions.md` |
| Trust policy rejects AssumeRole | `aws sts assume-role ...` (fails before S3) |
| Bucket policy `Condition` (PrincipalOrgID, SourceVpce) excludes caller | read the policy `Condition` blocks |

## Diagnosis Order

1. Confirm it is actually cross-account (compare principal account vs bucket owner).
2. Verify the bucket policy grants the caller — most failures are here.
3. Verify the caller's IAM allows the action.
4. If reads fail on objects A wrote, check object ownership / ACLs.
5. If the object is SSE-KMS, the KMS key must also be shared (separate grant).

Always verify with a read-only `head-object` or `s3 ls` before recommending any
policy change, and have the user review changes with their security team.
