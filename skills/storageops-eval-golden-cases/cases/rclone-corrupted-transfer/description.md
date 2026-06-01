# Case: rclone Corrupted on Transfer (S3-Compatible Provider)

## Scenario

用户使用 rclone 在两个 S3-compatible endpoint 之间 copy 文件，rclone 报 `corrupted on transfer: md5 hash differ`。文件大小相同但 checksum 不匹配。源和目标都是 S3-compatible provider（非 AWS S3）。

## What It Tests

- 正确识别 rclone corrupted-on-transfer 不是网络损坏
- 识别 multipart ETag 格式差异为根因
- 不误判为网络传输损坏
- 给出 `--s3-use-multipart-etag=false` 等 rclone 特定建议

## Expected Diagnosis

category: cli_sdk_behavior / subcategory: rclone
root cause: rclone 比较 multipart ETag 时源和目标的 ETag 格式不同（provider 差异）
recommendation: --ignore-checksum 或 --s3-use-multipart-etag=false

## Difficulty

medium

## Domains Tested

- cli_sdk_diagnosis
- rclone
- checksum_etag
