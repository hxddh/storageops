# Policy Evaluation

## Order
Evaluate deny/allow layers in this order: explicit deny, organization/SCP, identity IAM policy, bucket policy, ACL, block public access, and service-specific controls such as KMS or VPC endpoint policy.

## Evidence
Collect principal, action, resource ARN, error code, request ID, and relevant policy statements before recommending changes.
