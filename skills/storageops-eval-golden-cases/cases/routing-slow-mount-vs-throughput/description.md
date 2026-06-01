# Case: Routing Slow Mount vs Throughput

## Scenario
The user reports `git status` slowness on an object-storage-backed mount.

## What It Tests
- Routes metadata-heavy filesystem complaints to the mount skill.
- Avoids treating the issue as generic bandwidth tuning.

## Expected Diagnosis
Route to `storageops-mount-filesystem-workspace`.

## Difficulty
medium

## Domains Tested
- mount_filesystem_workspace
