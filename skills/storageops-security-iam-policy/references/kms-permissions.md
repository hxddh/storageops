# KMS Permissions

For SSE-KMS objects, having the right S3 permission is necessary but NOT
sufficient. The caller also needs KMS permissions on the specific key. A 403 can
come from the KMS layer even when every S3 policy is correct.

(See `references/kms-sse.md` for SSE types and ETag/throttling behavior. This file
focuses on the permission model and on telling KMS denials from S3 denials.)

## Two Policies Must Agree

SSE-KMS access is gated by two independent things:

1. **The S3 action** (`s3:GetObject`, `s3:PutObject`) via IAM and/or bucket policy.
2. **The KMS key authorization**, granted by EITHER:
   - the **key policy** (resource policy on the key), AND/OR
   - the caller's **IAM policy** with KMS actions — but IAM only works if the key
     policy delegates to IAM (most default key policies include the
     "enable IAM policies" / root statement; restrictive custom key policies may not).
   - a **KMS grant** (`aws kms create-grant`) for programmatic/temporary access.

So a caller can hold `kms:Decrypt` in IAM and still be denied if the key policy
does not allow IAM delegation.

## Required KMS Actions

- **Read (GetObject)** of an SSE-KMS object: `kms:Decrypt`.
- **Write (PutObject)** with SSE-KMS: `kms:GenerateDataKey` (and usually
  `kms:Decrypt` for multipart/overwrite flows).
- Bucket-level S3 Bucket Keys reduce KMS call volume but require the same actions.

## ViaService Condition

Key policies/grants often restrict KMS use to S3 only:
```json
"Condition": {
  "StringEquals": {"kms:ViaService": "s3.us-east-1.amazonaws.com"}
}
```
This means the principal may decrypt **through S3** but not call KMS directly.
A region mismatch (`s3.us-west-2...` vs the request region) silently denies. If
the key and bucket are in different regions, the `ViaService` value must match the
request's region.

## Cross-Account KMS

When account A reads B's SSE-KMS object, B must grant A on TWO resources:
- the bucket policy (`s3:GetObject`), and
- the KMS key (key policy statement or grant allowing A's principal `kms:Decrypt`).
A must also allow `kms:Decrypt` in its own IAM. Missing the KMS half is the classic
"bucket policy is right but still 403" case.

## Mapping the 403 to KMS vs S3

1. **Identify SSE first.** A head-object shows the encryption used:
   ```
   aws s3api head-object --bucket <b> --key <k> \
     --query '{sse:ServerSideEncryption, key:SSEKMSKeyId}'
   ```
   `aws:kms` → KMS is in play. `AES256`/empty → it is NOT a KMS problem.
2. **Read the error wording.** KMS denials usually name KMS:
   `KMS.AccessDeniedException`, "ciphertext refers to a customer master key that
   does not exist", "not authorized to perform: kms:Decrypt". S3-only denials say
   "not authorized to perform: s3:GetObject".
3. **Inspect the key policy / grants (read-only):**
   ```
   aws kms get-key-policy --key-id <key-arn> --policy-name default
   aws kms list-grants --key-id <key-arn>
   ```
4. **Simulate the KMS action:**
   ```
   aws iam simulate-principal-policy \
     --policy-source-arn <principal> --action-names kms:Decrypt \
     --resource-arns <key-arn>
   ```

## Diagnostic Checklist

1. Is the object actually SSE-KMS? (head-object)
2. Does the caller have `kms:Decrypt` (read) / `kms:GenerateDataKey` (write)?
3. Does the key policy allow that principal, or delegate to IAM?
4. Does a `kms:ViaService` / region condition match the request?
5. Cross-account: is the key shared in addition to the bucket?
6. Is the key enabled and in the same region as the request?
