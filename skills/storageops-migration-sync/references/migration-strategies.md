# Migration Strategies

## When to read
Use when selecting between server-side copy, direct client transfer, and offline/bulk migration.

## Options
- Server-side copy: fastest when source and destination support compatible APIs and same-region paths.
- Direct client transfer: flexible, but bandwidth and local reliability matter.
- Offline/bulk: best for very large datasets or constrained networks.

## Decision factors
Data size, object count, metadata fidelity, downtime tolerance, bandwidth, egress cost, and verification requirements.
