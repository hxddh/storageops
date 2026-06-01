# Provider IAM Differences

S3-compatible providers differ in IAM, ACL, bucket policy, and KMS semantics. Do not assume AWS SCP, KMS, or Block Public Access exists on BOS/OSS/COS/MinIO. Map the provider's native identity and bucket authorization model before recommending changes.
