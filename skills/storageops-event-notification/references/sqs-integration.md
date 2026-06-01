# SQS Integration

## When to read
Use when SQS remains empty despite object events.

## Checks
- Queue policy allows the object-storage service to send messages.
- Queue ARN, region, and account are correct.
- Encryption/KMS policy permits the service principal when SSE is enabled.
- Dead-letter queue and message retention settings do not hide delivery.
