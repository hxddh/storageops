# Event Notification Provider Compatibility

## When to read
Use for BOS, OSS, COS, MinIO, or other S3-compatible event systems.

## Notes
- Event names and payload schemas vary by provider.
- Some providers route through cloud-native event buses rather than AWS SNS/SQS/Lambda.
- Prefix/suffix filter semantics and retry guarantees can differ.

## Routing
If the failure is target permissions, use this skill; if it is endpoint/signature related, route to protocol or network skills.
