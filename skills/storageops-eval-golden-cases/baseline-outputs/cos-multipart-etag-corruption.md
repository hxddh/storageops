# Summary

Category: cli_sdk_behavior
Route: storageops-cli-sdk-diagnosis
Confidence: 0.85
Root Cause Type: multipart_etag_not_md5

The object is intact. rclone's generic `s3` backend compared the source MD5 to a
COS multipart ETag and falsely reported `corrupted on transfer`. The destination
host is a Tencent COS endpoint (`myqcloud.com`), and COS — like AWS — returns a
non-MD5 multipart ETag, so a plain MD5 comparison can never match. This is a
provider ETag-compatibility quirk, not data corruption.

# Key Evidence

- The destination ETag `"5d41402abc4b2a76b9719d911017c592-17"` carries a `-17`
  multipart suffix, so it is a multipart ETag, not the object MD5.
- The endpoint is `examplebucket-1250000000.cos.ap-guangzhou.myqcloud.com` — a COS
  (Tencent) endpoint, accessed through rclone's generic `s3` backend (provider
  Other), not the native `tencentcos` backend.
- The same 9134 MiB, 17-part object copies cleanly with `coscmd`, and a HEAD shows
  the object present with a matching byte size — consistent with a verification
  artifact, not a corrupt upload.

# Remediation

- Use the native Tencent backend: set rclone `type = tencentcos` (or `provider =
  TencentCOS`) so rclone applies COS-aware ETag/checksum handling instead of an
  MD5 comparison.
- If you must keep the generic `s3` backend, disable the ETag check (rclone
  `--ignore-checksum` / `ignore_checksum = true`) so a non-MD5 multipart ETag does
  not trigger a false corruption error.
- Verify integrity properly when needed: compare a real checksum (stored checksum
  metadata via HEAD / `get-object-attributes`) rather than the multipart ETag. Do
  not re-upload or remove the object on the strength of an ETag-vs-MD5 mismatch.
