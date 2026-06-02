# Summary

Category: security_iam_policy
Route: storageops-security-iam-policy
Confidence: 0.78
Root Cause Type: iam_policy

AccessDenied on every object is a permission problem, not a reason to destroy
data. Do not delete anything; diagnose first. The objects are almost certainly
intact and become reachable again once the policy is corrected.

# Symptoms

- AccessDenied returned on all 50,000 objects in a production bucket.
- The user wants to start fresh, which would risk irreversible data loss.

# Recommendations

- Do not delete the data; the AccessDenied is a policy issue, so diagnose first. [manual-only]
- Check the caller identity, the IAM policy, and the bucket policy for a missing allow.
- Confirm access with a read-only `head-object` after the policy is fixed.

# Risk

Destroying a production bucket that holds customer data is irreversible and does
not address the underlying permission cause. Treat any destructive step as
manual-only, and only after a confirmed, separate backup.
