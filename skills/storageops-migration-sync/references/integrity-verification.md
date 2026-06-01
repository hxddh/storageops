# Integrity Verification

## When to read
Use after or during migration to validate completeness and detect corruption.

## Checks
- Compare object count and total bytes by prefix.
- Sample object HEAD metadata and sizes.
- Use provider inventory where available.
- Treat multipart ETag mismatches carefully; use explicit checksums where possible.
