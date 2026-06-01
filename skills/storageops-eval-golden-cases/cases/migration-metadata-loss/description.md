# Case: Migration Metadata Loss

## Scenario
A cross-provider copy preserved object bytes but dropped content type and cache-control metadata.

## What It Tests
- Migration skill handles metadata parity, not only byte counts.
- Recommends dry-run comparison and metadata-aware recopy/update.

## Expected Diagnosis
Identify metadata loss during migration and recommend comparing HEAD metadata and rerunning with metadata preservation.

## Difficulty
medium

## Domains Tested
- migration_sync
