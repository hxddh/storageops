# Summary

Category: security_iam_policy
Route: storageops-security-iam-policy
Confidence: 0.86
Root Cause Type: iam_policy

The ListBuckets call returns 403 AccessDenied because the credential in use
lacks the required IAM permission. The botocore debug log also printed the
access key and secret in clear text, so the credential must now be treated as
leaked.

# Symptoms

- `aws s3 ls` (ListBuckets) returns 403 AccessDenied.
- The debug output exposed the AccessKeyId and SecretAccessKey in plaintext.

# Safety

A live credential was leaked into the debug log. This diagnosis never reproduces
the key material; a redacted fingerprint is enough to identify it. Anyone who
saw the log now holds the secret.

# Recommendations

- Rotate the leaked credential immediately: deactivate it, create a replacement,
  and update callers. [manual-only]
- After rotation, grant the caller an IAM policy allow for `s3:ListAllMyBuckets`
  and retry.
- Scrub the credential from any stored logs or shell history.
