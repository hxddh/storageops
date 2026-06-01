# S3A Connection Pool

## When to read
Use when jobs hang, timeout, or report `Unable to execute HTTP request` under parallel reads/writes.

## Checks
- Compare executor/task concurrency with S3A connection pool size.
- Look for socket timeout, connection acquisition timeout, and retry amplification.
- Check whether small files create many concurrent GET/HEAD/LIST operations.

## Safe tuning
Increase pool size gradually, add exponential backoff, and validate with one representative stage before changing production defaults.
