# KMS Permissions

For SSE-KMS objects, S3 permission alone is not enough. The caller generally needs `kms:Decrypt` for reads and `kms:Encrypt`/`kms:GenerateDataKey` for writes on the relevant key.

Check key policy, IAM policy, grants, encryption context, and cross-account key ownership.
