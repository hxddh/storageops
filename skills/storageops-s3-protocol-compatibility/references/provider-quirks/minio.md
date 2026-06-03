# Provider-Specific Quirks: MinIO

## ETag Behavior

- **Single PUT:** Returns MD5 hash (32 hex chars) or SHA-256 depending on
  server configuration. MinIO can be configured to return ETags compatible
  with AWS S3.
- **Multipart Upload:** Returns ETag in AWS-compatible format (MD5 of
  concatenated part MD5s + `-N` suffix). (Verified — MinIO `internal/etag`
  implements `MD5(e1‖…‖eN)-N` for unencrypted multipart, 2026-06.)
- **MinIO is generally the most AWS S3-compatible** among non-AWS providers
  for ETag semantics.

## Tool Compatibility Matrix

| Tool | Native Support | Requires Config | Known Issues |
|------|---------------|-----------------|--------------|
| mc (MinIO Client) | ✅ Native | `mc alias set` | Best for MinIO |
| rclone | ✅ Via S3 compat | `type = s3`, `provider = Minio` | Very reliable |
| s5cmd | ✅ Via S3 compat | `--endpoint-url` | Generally works well |
| awscli | ✅ Via S3 compat | `--endpoint-url`, `--region` | Works with SigV4 |
| boto3 | ✅ Via S3 compat | `endpoint_url`, `region_name` | Works with SigV4 |

## Signature (Auth) Behavior

- **Algorithm:** MinIO supports standard AWS SigV4 (both v2 and v4).
- This makes MinIO the simplest non-AWS provider for cross-tool access.
- **No custom auth headers:** MinIO does not use provider-specific headers.

## ListObjects Behavior

- Supports both V1 and V2 ListObjects fully.
- V2 behavior is very close to AWS S3.
- `max-keys` default: 1000.
- Pagination standard.
- Supports delimiter and prefix semantics identical to AWS S3.

## Multipart Upload

- **Part size:** Minimum 5 MiB (AWS-compatible).
- **Max parts:** 10,000.
- Standard lifecycle: Initiate → UploadPart → Complete/Abort.
- Full AWS S3 compatibility for multipart operations.

## Server-Side Copy

- Supports CopyObject and multipart copy within the same MinIO instance.
- Cross-instance copy may require direct network connectivity between instances.

## Bucket Versioning

- MinIO supports bucket versioning.
- Versioning must be explicitly enabled per bucket.
- Delete markers behave the same as AWS S3.

## Object Lock

- MinIO supports Object Lock (WORM) in enterprise editions.
- Requires bucket versioning to be enabled.
- Supports both Governance and Compliance modes.

## Storage Classes

MinIO does not have traditional storage classes like AWS S3.
Tiering is handled through MinIO's tiering / lifecycle transition features
(enterprise edition):
- Data can be transitioned to external storage (Azure, GCS, AWS S3, etc.).
- No built-in "IA" or "Glacier" equivalent within MinIO itself.

## Deployment-Specific Considerations

### Single-Node vs Distributed
- Distributed MinIO uses erasure coding across multiple disks.
- Single-node MinIO has no redundancy (use only for testing).

### TLS Configuration
- MinIO generates self-signed certs by default.
- For self-signed certs, install the CA bundle or trust root and keep TLS verification enabled in production.
- Production MinIO should use valid CA-signed certificates.

### Ports
- Default API port: 9000.
- Console (Web UI) port: 9001.
- Ensure the correct port is used in endpoint URLs for API access.

## Known Issues with Cross-Tool Access

1. **Self-signed certificates:** Most tools will reject MinIO's default
   self-signed TLS certificate. Fix: add the CA to the system trust store,
   use `--ca-cert` in rclone, or configure valid certificates.

2. **Region requirement:** Even though MinIO may not strictly require a
   region, SigV4 signing requires one. Always pass `--region us-east-1`
   (or equivalent) when using AWS tools against MinIO.

3. **Path-style vs virtual-hosted:** MinIO supports both. path-style is
   default for custom endpoints: `https://minio.example.com:9000/bucket/key`.

4. **STS and IAM:** MinIO's IAM implementation differs from AWS IAM.
   AWS IAM policy documents may not apply directly to MinIO.
