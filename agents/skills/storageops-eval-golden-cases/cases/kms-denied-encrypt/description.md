# Case: KMS Key Denied for SSE-KMS Encryption

## Situation

An application role in account 123456789012 is trying to upload objects to an S3 bucket that
uses SSE-KMS with a KMS key owned by a different account (987654321098). The upload fails with
AccessDenied because the IAM policy for the application role has an explicit Deny on
`kms:*` for keys not owned by account 123456789012.

## Root Cause

An explicit Deny overrides any Allow. The IAM policy has:
```
Deny kms:* where kms:CallerAccount != 123456789012
```

Since the KMS key is in account 987654321098, this condition is met and the Deny applies.
S3 SSE-KMS requires `kms:GenerateDataKey` to encrypt and `kms:Decrypt` to read.
Both are blocked by the explicit Deny.

## Expected Diagnosis

- Category: security_iam_policy
- Subcategory: KMS denied + explicit deny
- Root cause: explicit IAM Deny blocks cross-account KMS key access
- Confidence: high
