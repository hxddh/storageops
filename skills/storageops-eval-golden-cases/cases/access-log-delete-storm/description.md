# Case: Access Log Delete Storm

## Scenario
Objects are missing, and access logs show a short burst of DELETE requests from one role.

## What It Tests
- Access log aggregation by operation, requester, and time window.
- Safety-aware remediation for accidental deletes.

## Expected Diagnosis
Identify a DELETE storm from a cleanup role and recommend pausing the job, preserving logs, and restoring from version history if available.

## Difficulty
medium

## Domains Tested
- access_log_analysis
