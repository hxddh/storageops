# Summary

Category: cors_configuration
Route: storageops-s3-protocol-compatibility
Confidence: 0.86
Root Cause Type: cors_method_not_allowed

Primary Diagnosis: root_cause_type=cors_method_not_allowed, affected_layer=policy

Browser PUT preflight fails because the bucket CORS rule allows GET/HEAD but not PUT
for the app origin.

# Key Evidence

- Preflight reports `Method PUT is not allowed by Access-Control-Allow-Methods`.
- `Access-Control-Allow-Origin` is present for the app origin.
- Direct GET without an Origin header succeeds.

# Remediation

Update the bucket CORS configuration with `put-bucket-cors` to include `PUT` in `AllowedMethod` for the
narrow app origin. Retest with an OPTIONS preflight before retrying the browser upload.
