# Summary
Category: network_endpoint_access
Route: storageops-network-endpoint-access
Confidence: 0.82
Root Cause Type: tls_certificate_expired
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=tls_certificate_expired, affected_layer=tls

The TLS/SSL handshake fails because the certificate chain is rejected — typically an
expired endpoint certificate or a stale local CA bundle.

# Key Evidence
- The error is a TLS/SSL certificate verification failure (expired / not-trusted),
  before any S3 request is processed.

# Remediation
- Check the certificate notAfter date, then update the local CA bundle (ca-bundle / certifi) and re-verify (e.g. the certifi package) and system trust store; if the
  endpoint certificate itself is expired, the provider must renew it. Do not skip
  verification as a fix.
