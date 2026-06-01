# Case: Routing Access Log 503

## Scenario
The user has access logs showing a 503 spike and asks who or what caused it.

## What It Tests
- Routes log aggregation questions to access-log analysis first.
- Allows later escalation to performance diagnosis after requester grouping.

## Expected Diagnosis
Route to `storageops-access-log-analysis`.

## Difficulty
medium

## Domains Tested
- access_log_analysis
