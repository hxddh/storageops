# Case: Routing Consistency Stale Read

## Scenario
The user reads old object content after a successful overwrite.

## What It Tests
- Routes stale-read and cache-layer questions to data consistency.
- Avoids treating the issue as pure CLI behavior.

## Expected Diagnosis
Route to `storageops-data-consistency`.

## Difficulty
medium

## Domains Tested
- consistency_integrity
