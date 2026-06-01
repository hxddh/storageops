# Provider Domains

## Provider hints
- AWS S3: `s3.amazonaws.com`, `x-amz-*`, CloudTrail, IAM/KMS/SCP.
- Baidu BOS: `bcebos`, `x-bce-*`, bcecmd.
- Alibaba OSS: `aliyuncs.com`, OSS Log Service, ossutil.
- Tencent COS: `myqcloud.com`, COS event/log formats.
- MinIO/custom S3: custom endpoint, path-style, self-signed TLS, SigV4 compatibility.

Use provider identification to choose protocol quirks and references, not to skip evidence collection.
