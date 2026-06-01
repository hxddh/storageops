# Case: Cross-Account S3 Access Denied — Missing Bucket Policy

## Scenario

Account A (111111111111) 的 IAM user `alice` 需要读取 Account B (222222222222) 的 bucket `shared-data` 中的对象。Account B 的 bucket policy 允许 Account A 访问，但 alice 仍然收到 403 AccessDenied。

## What It Tests

- 正确识别跨账号访问需要两个 Allow：bucket policy (Account B) + IAM policy (Account A)
- 识别只有一方 Allow 不够
- 不会建议将 bucket 设为 public
- 给出正确的 policy 修改建议 (manual-only)

## Expected Diagnosis

category: security_iam_policy / subcategory: access_denied
root cause: Account B 的 bucket policy Allow 了 Account A，但 Account A 没有在自己的 IAM policy 中授予 alice s3:GetObject 权限。跨账号访问需要双方都 Allow。

## Difficulty

easy

## Domains Tested

- security_iam_policy
- access_denied
- bucket_policy
