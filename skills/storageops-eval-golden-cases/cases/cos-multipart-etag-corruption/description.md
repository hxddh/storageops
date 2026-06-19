# Case: COS Multipart ETag False "Corruption" via Non-Native Tool

## Scenario

A user copies a large object to Tencent Cloud COS using `rclone` with the generic
`s3` backend (SigV4 against the `myqcloud.com` endpoint). rclone reports the
transfer as `corrupted on transfer` because the destination ETag does not equal
the source MD5 — but the object is intact. COS (like AWS) returns a non-MD5
multipart ETag, and the generic S3 backend verifies it as if it were an MD5.

## What It Tests

- Provider detection: the endpoint host is a COS (`myqcloud.com`) endpoint, not AWS.
- Recognizing a provider ETag-compatibility quirk rather than real data corruption.
- Recommending the native `tencentcos` rclone backend (or disabling checksum
  verification) instead of re-uploading or deleting data.

## Expected Diagnosis

Not corruption: the COS multipart ETag is not the object MD5, so a generic-tool
checksum comparison falsely fails. Use the native backend or skip the ETag check.

## Difficulty

medium

## Domains Tested

- cli_sdk_behavior
- s3_protocol_compatibility (provider quirk)
