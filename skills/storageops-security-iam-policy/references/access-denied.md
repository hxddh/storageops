# Access Denied Diagnosis

## The 403 Response

### AWS S3 403 Format
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Error>
  <Code>AccessDenied</Code>
  <Message>Access Denied</Message>
  <RequestId>request-id</RequestId>
  <HostId>host-id</HostId>
</Error>
```

**Note:** AWS S3 intentionally does NOT provide detailed reasoning for AccessDenied
to avoid information leakage. The same `AccessDenied` error can mean:
- IAM policy missing Allow.
- Bucket policy explicit Deny.
- ACL restriction.
- Block Public Access.
- KMS key access denied.
- Object does not exist (403 instead of 404 for anonymous/unauthenticated requests).

### S3-Compatible Provider Differences
Some providers include additional detail:
- `Message: Access Denied - insufficient permission for action s3:GetObject`
- Custom error codes: `PermissionDenied`, `UnauthorizedAccess`.

## When 403 = "Object Doesn't Exist" (Misleading)

For anonymous or unauthenticated requests:
- A non-existent object returns 403 (AccessDenied), not 404 (NoSuchKey).
- This prevents object existence enumeration.
- For authenticated requests with `s3:ListBucket` permission, a non-existent object returns 404.

### Check
- If you have `s3:GetObject` permission but no `s3:ListBucket`, a 403 on GetObject for a non-existent key is expected.
- Solution: add `s3:ListBucket` to distinguish 403 from 404.

## Denial Source Identification

### 1. IAM Policy Denial
```json
{
  "Effect": "Deny",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::bucket/*"
}
```
This EXPLICITLY denies GetObject for all objects in the bucket. No Allow can override this.

### 2. Missing Allow
If NO policy statement allows the action, it is implicitly denied.
Solution requires adding an Allow statement.

### 3. Bucket Policy Denial
```json
{
  "Effect": "Deny",
  "Principal": {"AWS": "arn:aws:iam::123456789012:user/alice"},
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::bucket/*"
}
```
Even if Alice's IAM policy allows GetObject, the bucket policy Deny overrides.

### 4. ACL Denial
- Bucket ACL and Object ACL can grant READ/WRITE/FULL_CONTROL.
- ACL is the legacy access control mechanism; bucket policy and IAM policy are preferred.
- If ACL is set to `private`, only the bucket owner can access.

### 5. Condition Key Mismatch
```json
{
  "Effect": "Allow",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::bucket/*",
  "Condition": {
    "IpAddress": {"aws:SourceIp": "10.0.0.0/8"}
  }
}
```
Access is allowed ONLY from the 10.0.0.0/8 IP range. Outside → implicit Deny.

Common condition keys:
- `aws:SourceIp` — Client IP must match.
- `aws:SourceVpc` — Request must come from a specific VPC.
- `aws:SourceVpce` — Request must come through a specific VPC endpoint.
- `s3:x-amz-server-side-encryption` — Objects must (or must not) have specific SSE.
- `s3:x-amz-acl` — PUT with specific ACL.

### 6. Block Public Access
S3 Block Public Access settings override any Allow:
- `BlockPublicAcls` — Ignore public ACLs.
- `IgnorePublicAcls` — Ignore public ACLs (don't evaluate).
- `BlockPublicPolicy` — Block bucket policies with public principals.
- `RestrictPublicBuckets` — Restrict access to public buckets to only AWS services and authorized users.

### 7. SCP (Service Control Policy)
- Organization-level policy that limits permissions.
- Even if IAM and bucket policy Allow, SCP Deny overrides.
- Typically not visible to bucket owners.

## Diagnostic Questions

1. Is the principal authenticated or anonymous?
2. Does the IAM policy have an explicit Allow for this action and resource?
3. Does the IAM policy have an explicit Deny?
4. Does the bucket policy have a Deny?
5. Does the bucket policy have an Allow (for cross-account)?
6. Are there condition keys that might not match?
7. Is Block Public Access enabled?
