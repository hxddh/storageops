# 摘要

Category: cli_sdk_behavior
Route: storageops-cli-sdk-diagnosis
Confidence: 0.82
Root Cause Type: tool_sdk_incompatibility

rclone reports `corrupted on transfer` because it compares an ETag from one side
with a multipart ETag from the other side.

# 诊断结论

The evidence points to rclone/S3 ETag compatibility, not proven data loss. The
destination value has multipart shape such as `md5-3` after server-side copy.

# 关键证据

- Tool: rclone.
- Error: corrupted on transfer.
- Checksum source: ETag.
- Destination style: multipart ETag with `-3` suffix and MD5-like prefix.

# 修复建议

First verify one sample object by byte hash or provider checksum. Then retry with
`--s3-use-multipart-etag=false`; use `--ignore-checksum` only as a last resort.
