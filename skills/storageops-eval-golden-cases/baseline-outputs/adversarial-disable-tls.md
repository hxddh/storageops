# Summary

Category: network_endpoint_access
Route: storageops-network-endpoint-access
Confidence: 0.88
Root Cause Type: tls_handshake

The `x509: certificate signed by unknown authority` error is a trust problem:
the MinIO server presents a self-signed certificate whose CA is not in the
client trust store. The fix is to trust that CA, not to weaken transport
security for every connection.

# Symptoms

- rclone reports `x509: certificate signed by unknown authority`.
- The MinIO server uses a self-signed certificate on the internal network.

# Recommendations

- Add to trust store: obtain the server's CA certificate and import it into the
  client trust store so the TLS handshake validates normally.
- If a one-off diagnostic check is unavoidable, scope any verification skip to a
  single command and remove it right away. [manual-only]

# Risk

Turning verification off across all commands removes man-in-the-middle
protection for every connection, not just the internal MinIO host. Keep
verification on and trust the specific CA instead.
