# Summary

Category: cors_configuration
Route: storageops-s3-protocol-compatibility
Confidence: 0.88
Root Cause Type: missing_cors_configuration

Browser preflight fails because the bucket has no CORS rule, surfaced as
`NoSuchCORSConfiguration`.

# Key Evidence

- The browser expects `Access-Control-Allow-Origin`.
- The API response reports `NoSuchCORSConfiguration`.
- The repair path is bucket CORS configuration, not bucket deletion.

# Recommendations

Use `put-bucket-cors` with a narrow `AllowedOrigin` and the required
`AllowedMethod` values. Verify IAM/object access separately before retesting CORS.
