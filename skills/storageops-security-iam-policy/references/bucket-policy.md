# Bucket Policy Analysis

## Policy Structure

```json
{
  "Version": "2012-10-17",
  "Id": "PolicyId",
  "Statement": [
    {
      "Sid": "StatementId",
      "Effect": "Allow|Deny",
      "Principal": {"AWS": "arn:aws:iam::123456789012:root"},
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": ["arn:aws:s3:::bucket/*", "arn:aws:s3:::bucket"],
      "Condition": {
        "StringEquals": {"s3:x-amz-acl": "bucket-owner-full-control"}
      }
    }
  ]
}
```

## Key Elements

### Principal
Who the policy applies to:
- `"Principal": {"AWS": "arn:aws:iam::123456789012:user/name"}` — Specific user.
- `"Principal": {"AWS": "arn:aws:iam::123456789012:role/name"}` — Specific role.
- `"Principal": {"AWS": "arn:aws:iam::123456789012:root"}` — Entire account.
- `"Principal": "*"` — ANYONE (including anonymous). **HIGH SECURITY RISK.**
- `"Principal": {"Service": "cloudtrail.amazonaws.com"}` — AWS service.

### Action
- `"s3:*"` — All S3 actions. **Too broad.**
- `"s3:GetObject"` — Download objects.
- `"s3:PutObject"` — Upload objects.
- `"s3:DeleteObject"` — Delete objects.
- `"s3:ListBucket"` — List objects in bucket.
- `"s3:GetBucketLocation"` — Get bucket region.

### Resource
- `arn:aws:s3:::bucket` — The bucket itself (for ListBucket, GetBucketLocation).
- `arn:aws:s3:::bucket/*` — Objects in the bucket (for GetObject, PutObject).
- BOTH are needed for common access patterns.

### Condition
Context-based restrictions:
- `aws:SourceIp` — IP-based restriction.
- `aws:SourceVpc` / `aws:SourceVpce` — VPC-based restriction.
- `aws:PrincipalOrgID` — AWS Organization restriction.
- `s3:x-amz-server-side-encryption` — Require SSE.
- `s3:x-amz-acl` — Restrict ACL.
- `s3:signatureAge` — Pre-signed URL expiry.
- `s3:authType` — Authentication method.

## Common Policy Patterns

### Read-Only Access (Public Bucket — DANGEROUS)
```json
{
  "Effect": "Allow",
  "Principal": "*",
  "Action": ["s3:GetObject"],
  "Resource": "arn:aws:s3:::public-bucket/*"
}
```
**WARNING:** This makes all objects publicly readable. Only use for intentionally public content.

### Cross-Account Access
```json
{
  "Effect": "Allow",
  "Principal": {"AWS": "arn:aws:iam::222222222222:root"},
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": ["arn:aws:s3:::bucket", "arn:aws:s3:::bucket/*"]
}
```
This allows account 222222222222 to access the bucket. That account must ALSO grant its users/roles `s3:GetObject` and `s3:ListBucket` in their IAM policies.

### Require SSE
```json
{
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:PutObject",
  "Resource": "arn:aws:s3:::bucket/*",
  "Condition": {
    "StringNotEquals": {"s3:x-amz-server-side-encryption": "AES256"}
  }
}
```
Denies PUT without SSE-S3 encryption.

### IP Restriction
```json
{
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": "arn:aws:s3:::bucket/*",
  "Condition": {
    "NotIpAddress": {"aws:SourceIp": ["10.0.0.0/8", "172.16.0.0/12"]}
  }
}
```
Denies access from outside specific IP ranges.

## Policy Validation Checklist

1. Do Action and Resource align? (GetObject → object ARN, ListBucket → bucket ARN)
2. Is the Principal correct? (User ARN vs Role ARN vs Account root)
3. Are there conflicting Allow/Deny statements?
4. Are conditions overly restrictive or overly permissive?
5. Is `"Principal": "*"` intentional and safe?
6. Does this policy comply with least privilege?
