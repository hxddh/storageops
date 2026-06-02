# Summary

Category: security_iam_policy
Route: storageops-security-iam-policy
Confidence: 0.82
Root Cause Type: iam_policy

The Lambda function fails with 403 because its execution role lacks an IAM allow
for `s3:GetObject`, not because the bucket is private. The bucket policy added a
wildcard `Principal": "*"`, which does not grant the Lambda access and is itself
a serious security risk.

# Symptoms

- Lambda reads from `my-app-data` and gets 403 AccessDenied.
- The bucket policy grants `Principal": "*"` yet access still fails.

# Risk

A wildcard `Principal": "*"` exposes objects to anyone on the internet while
doing nothing for the Lambda's access. Block Public Access should stay enabled.
The wildcard grant is the security risk here, not the solution.

# Recommendations

- Remove wildcard principal from the bucket policy.
- Grant access through the Lambda execution role: attach an IAM role policy that
  allows `s3:GetObject` on `arn:aws:s3:::my-app-data/*`.
- Keep the bucket private with Block Public Access enabled.
