# Rclone Migration Guide

## When to read
Use when rclone is selected for cross-provider migration.

## Safe baseline
Start with dry-run, low concurrency, explicit checksum/size verification, and logs enabled. Increase concurrency only after stable throughput is observed.

## Evidence
Ask for rclone version, remote config type, flags, error excerpt, object count, size distribution, and observed throughput.
