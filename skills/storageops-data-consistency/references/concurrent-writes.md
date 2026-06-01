# Concurrent Writes

## When to read
Use when multiple writers overwrite the same object or users report lost updates.

## Model
Object storage does not provide POSIX file locks. Last writer wins unless the application uses conditional writes, object versioning, or external coordination.

## Evidence
Ask for writer identities, timestamps, version IDs, ETags, and whether conditional headers were used.
