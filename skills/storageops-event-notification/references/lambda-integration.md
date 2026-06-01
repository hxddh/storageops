# Lambda Integration

## When to read
Use when the notification target is Lambda.

## Checks
- Lambda resource policy allows the bucket service principal.
- Function region matches the bucket/event source constraints.
- Concurrency, DLQ, and recent errors are inspected.
- Prefix/suffix filters match the object key.
