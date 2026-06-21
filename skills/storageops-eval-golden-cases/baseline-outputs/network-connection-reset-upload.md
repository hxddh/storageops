# Summary

Category: network_endpoint_access
Route: storageops-network-endpoint-access
Confidence: 0.85
Root Cause Type: middlebox_transport_reset
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=middlebox_transport_reset, affected_layer=network

Large uploads are being reset by something in the network path, not by S3 auth or
storage. The pattern — large multipart PUTs failing mid-transfer with "connection
reset by peer" / "broken pipe" while small PUTs and all downloads succeed, starting
right after a new firewall/NAT appliance was inserted — points to a middlebox
transport limit: an idle/connection timeout, MTU/MSS mismatch, or NAT
connection-tracking limit cutting the long-lived large-upload connections.

# Key Evidence

- Errors are "Connection reset by peer" (ECONNRESET) and "broken pipe" (EPIPE)
  mid-transfer — transport resets, not 4xx auth responses.
- Only large/multipart uploads fail; small uploads and all downloads succeed, so the
  break correlates with connection duration/size, not credentials or the bucket.
- The failures began when a new firewall/NAT appliance entered the path, and the
  same client works from a different network segment — isolating the cause to the
  path, not the endpoint or the application.

# Remediation

- Check the middlebox for an idle/connection **timeout** and a NAT
  connection-tracking limit that would drop long-lived uploads; raise the timeout or
  exempt the storage endpoint on the **firewall**.
- Test for an **MTU**/MSS mismatch (PMTUD black hole): try a lower MTU / enable
  MSS clamping on the appliance, or test with a smaller multipart chunk size to see
  if resets stop.
- Confirm with a path capture (reset packets / where the RST originates) and by
  retrying from a segment that bypasses the appliance. Do not rotate credentials or
  change the bucket policy — auth is not the cause.
