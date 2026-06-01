# Cross-Account Access

Cross-account S3 access needs both sides: the caller identity policy must allow the S3 action, and the bucket policy must trust the caller principal or account. KMS-encrypted objects also require key policy or grants for the caller.

Validate with a read-only command such as `aws s3api head-object` or `aws s3 ls` before changing policies.
