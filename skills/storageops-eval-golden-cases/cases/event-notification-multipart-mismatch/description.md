# Case: Lambda Not Triggered on Multipart Upload (event-type mismatch)

## Scenario
A thumbnailer Lambda fires for small (single-PUT) images but never for large
images uploaded via the multipart API. The bucket notification configures only
`s3:ObjectCreated:Put`.

## What It Tests
- Identifies the root cause as event-type mismatch: multipart uploads emit
  `s3:ObjectCreated:CompleteMultipartUpload`, not `:Put`.
- Not a permission/IAM problem, not corruption.
- Recommends adding `CompleteMultipartUpload` (or `s3:ObjectCreated:*`).
- Confirmable offline with `scripts/notification_config_analyzer.py`.

## Difficulty
medium
