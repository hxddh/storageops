# Routing
Category: access_log_analysis
Route: storageops-access-log-analysis
Confidence: 0.75
Root Cause Type: error_spike

A 503 spike to analyze across access logs routes to access-log-analysis: parse the
logs to find the top requester and operation mix behind the errors.

# Evidence Gaps
- Need the raw access logs (S3 server access logs) for the window, so the parser can
  attribute the 503s to a top requester and operation.
