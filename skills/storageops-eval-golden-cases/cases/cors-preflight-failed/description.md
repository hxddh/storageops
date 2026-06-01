# Case: cors-preflight-failed

## Summary

A web application on `https://app.example.com` uploads assets to S3 and
displays them in the browser. The images load when accessed directly but
JavaScript `fetch()` calls are blocked by the browser with a CORS policy error.

## Root Cause

The S3 bucket has no CORS configuration (`NoSuchCORSConfiguration`). Without
a CORS configuration, S3 does not include `Access-Control-Allow-Origin` headers
in responses, so the browser blocks cross-origin responses.

The bucket policy allows `s3:GetObject` to `*` (public read), so the object
itself is accessible — but CORS headers are a separate S3 configuration layer
independent of access control.

## Expected Diagnosis

- Category: s3_protocol_compatibility, subcategory: cors
- Root cause: CORS configuration is absent on the bucket
- Remediation: Add a CORS configuration with appropriate `AllowedOrigin` and `AllowedMethod` entries (manual-only)
- Note: Adding CORS does not affect access control — that is governed by bucket policy

## Key Trap

The curl preflight returns 403, which might suggest an access control issue.
But the 403 is because S3 returns errors without CORS headers — the underlying
object IS accessible (confirmed by the direct GET returning 200). The real issue
is the missing CORS configuration, not permissions.
