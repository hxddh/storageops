# Case: Routing Migration Checksum

## Scenario
Cross-provider migration completes, but checksum verification fails on a subset.

## What It Tests
- Routes migration planning and verification to migration-sync.
- Allows secondary consistency analysis after migration context is captured.

## Expected Diagnosis
Route to `storageops-migration-sync`.

## Difficulty
medium

## Domains Tested
- migration_sync
