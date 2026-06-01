# Case: Multipart ETag Mismatch

## Scenario
A verification job treats multipart ETags as MD5 checksums and reports false corruption.

## What It Tests
- Distinguishes multipart ETag format from whole-object MD5.
- Recommends checksum metadata or provider-supported checksum APIs.

## Expected Diagnosis
Identify multipart ETag semantics as the likely cause, not data corruption by default.

## Difficulty
medium

## Domains Tested
- consistency_integrity
