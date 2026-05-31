# Case: integration-rclone-corrupted-to-report

## What this case tests
End-to-end multi-skill collaboration: triage → cli-sdk-diagnosis → 
s3-protocol-compatibility → evidence-reporting.

Tests that skills correctly route between each other and produce a coherent
final report when given realistic multi-domain evidence.

## Scenario
User reports rclone `corrupted on transfer: md5 hash differ` when copying
between two BOS buckets. The debug log shows server-side copy with ETag
format mismatch. User also mentions occasional 429 errors.

## Input
- rclone debug log (from `rclone-corrupted-transfer/input/rclone-debug.log`)
- User description: "rclone corrupted on transfer between two BOS buckets, 
  also seeing some 429 errors"
- Config: BOS endpoints, rclone v1.65.0

## Expected Diagnostic Flow
1. triage: classify as cli_sdk_behavior + s3_protocol_compatibility + 
   performance_throughput (429s)
2. Route to cli-sdk-diagnosis first (rclone error)
3. cli-sdk-diagnosis identifies ETag format mismatch → cross-route to 
   s3-protocol-compatibility
4. s3-protocol-compatibility checks BOS provider-quirks → confirms multipart 
   ETag behavior difference
5. performance-diagnosis analyzes 429 errors → identifies concurrency threshold
6. evidence-reporting combines into single diagnosis report

## Expected Final Report
- Primary root cause: BOS server-side copy uses multipart ETag format that 
  differs from rclone's single-PUT ETag expectation
- Secondary: concurrency causing 429 throttling
- Category: cli_sdk_behavior (primary), s3_protocol_compatibility (secondary)
- Confidence: >= 0.80 (multiple evidence items, provider-quirks match)
- Must reference: provider-quirks/bos.md, rclone.md, throughput-model.md
- Must include: both ETag fix AND concurrency tuning recommendations

## Multi-Skill Coverage Verified
- [x] triage routing accuracy
- [x] cli-sdk cross-domain routing to s3-protocol
- [x] s3-protocol provider-quirks matching
- [x] performance throttling analysis
- [x] evidence-reporting multi-domain synthesis
