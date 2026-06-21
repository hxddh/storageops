# Routing
Category: cors_configuration
Route: storageops-s3-protocol-compatibility
Confidence: 0.82
Root Cause Type: cors_rule_missing

A failing browser OPTIONS preflight is a CORS configuration problem, routed to
s3-protocol-compatibility: the bucket CORS rule must allow the method and origin.

# Evidence Gaps
- Need the bucket CORS configuration and the request Origin/method so the missing
  Access-Control-Allow-Origin / allowed-method rule can be identified.
