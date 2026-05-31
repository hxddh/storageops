# Case: tls-cert-expired

## What this case tests
Tests network-endpoint-access skill's ability to diagnose TLS certificate
expiration issues when connecting to object storage endpoints.

## Scenario
A user reports all connections to their S3-compatible endpoint failing with
TLS errors. They get "certificate has expired" from curl while other endpoints work fine.
The cert expired 3 days ago.

## Expected Diagnosis
- Category: network_endpoint_access
- Subcategory: tls
- Root cause: expired TLS certificate
- Confidence >= 0.85
