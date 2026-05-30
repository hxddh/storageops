# Case: TLS Certificate Expired

## Summary
All S3 HTTPS connections fail with `CERTIFICATE_VERIFY_FAILED: certificate has expired`.
Root cause is an outdated `certifi` CA bundle on the client (2022.12.7) whose trust anchors
do not cover the renewed endpoint certificate.

## Domain
`network_endpoint_access` — TLS/SSL handshake failure

## Root Cause
Outdated CA bundle (`certifi==2022.12.7`) causing TLS certificate verification failure.

## What the Agent Should Diagnose
1. Identify TLS certificate expiry error from the SSL output
2. Note the `notAfter` date showing the certificate expired on 2024-03-14
3. Identify outdated `certifi` as the client-side root cause
4. Recommend updating `certifi` to the latest version and verifying with `openssl s_client`
