# Case: s5cmd NoSuchKey Error

## Summary
User runs `s5cmd cp` on S3 objects and gets NoSuchKey 404 errors. The objects exist but
under a different path prefix (`exports/2024-backup/` vs `exports/2024/`).

## Domain
`cli_sdk_behavior` — s5cmd CLI tool, object path resolution

## Root Cause
Path mismatch: objects migrated to a different prefix after the copy command was written.

## What the Agent Should Diagnose
1. Identify s5cmd NoSuchKey errors
2. Note that the key does not exist at the specified path
3. Suggest verifying the actual prefix with `s5cmd ls` or `aws s3 ls`
4. Recommend updating copy paths to match the actual object location
