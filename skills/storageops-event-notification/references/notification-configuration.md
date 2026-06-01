# Notification Configuration

## When to read
Use when S3 event notifications do not fire or the user provides notification XML/JSON.

## Checks
- Event type matches the object operation.
- Prefix/suffix filters match the key exactly.
- Destination ARN/region/account is correct.
- Overlapping rules are supported by the provider.
