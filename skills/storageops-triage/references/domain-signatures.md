# Domain Signatures

## Error/status mapping
- 401/403, `AccessDenied`, `Unauthorized` → security-iam-policy.
- `SignatureDoesNotMatch`, `InvalidArgument`, `MalformedXML` → s3-protocol-compatibility.
- 429/503, `SlowDown`, `RequestRateLimitExceeded` → performance-diagnosis.
- DNS, TLS, connection timeout/refused → network-endpoint-access.
- rclone/s5cmd/awscli/boto3/s3cmd/bcecmd/obsutil errors → cli-sdk-diagnosis.

## Ambiguous cases
- 403 with signature text should route to protocol first, then security.
- Timeout with high RTT should involve network before performance tuning.
- ETag mismatch from a tool should involve CLI/SDK and protocol checksum references.
