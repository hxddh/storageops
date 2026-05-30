# S3 CORS (Cross-Origin Resource Sharing)

## Overview

Browsers enforce the Same-Origin Policy: JavaScript on `https://app.example.com`
cannot fetch `https://bucket.s3.amazonaws.com/file.jpg` by default. S3 CORS
configuration allows specific origins to make cross-origin requests.

---

## How S3 CORS Works

1. Browser sends a **preflight OPTIONS request** to the S3 endpoint with:
   - `Origin: https://app.example.com`
   - `Access-Control-Request-Method: GET`
   - `Access-Control-Request-Headers: content-type` (if applicable)

2. S3 checks the bucket CORS configuration. If a matching rule is found, it responds with:
   - `Access-Control-Allow-Origin: https://app.example.com`
   - `Access-Control-Allow-Methods: GET`
   - `Access-Control-Max-Age: 3000`

3. Browser sends the actual request. S3 must include `Access-Control-Allow-Origin` in the response.

4. If no matching CORS rule is found, S3 returns the response **without** CORS headers.
   The browser blocks the response and JavaScript sees a network error.

---

## CORS Configuration Example

```xml
<CORSConfiguration>
  <CORSRule>
    <AllowedOrigin>https://app.example.com</AllowedOrigin>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedMethod>PUT</AllowedMethod>
    <AllowedMethod>POST</AllowedMethod>
    <AllowedHeader>*</AllowedHeader>
    <ExposeHeader>ETag</ExposeHeader>
    <MaxAgeSeconds>3000</MaxAgeSeconds>
  </CORSRule>
</CORSConfiguration>
```

---

## Diagnostic Patterns

### Symptom: Browser console shows "No 'Access-Control-Allow-Origin' header"

```
Access to fetch at 'https://bucket.s3.amazonaws.com/object.jpg' from origin
'https://app.example.com' has been blocked by CORS policy: No
'Access-Control-Allow-Origin' header is present on the requested resource.
```

**Cause options:**
1. No CORS configuration on the bucket at all
2. CORS configuration exists but the origin does not match any `AllowedOrigin`
3. CORS configuration exists but the method does not match any `AllowedMethod`
4. S3 returned an error (4xx/5xx) — S3 does not add CORS headers to error responses

**Diagnosis:**
```
# manual-only: aws s3api get-bucket-cors --bucket <bucket>
```

**Simulate the preflight manually:**
```bash
curl -v -X OPTIONS \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: GET" \
  https://bucket.s3.amazonaws.com/object.jpg
```

Expected response includes `Access-Control-Allow-Origin` if CORS is configured correctly.

### Symptom: Preflight 403 even with CORS configured

**Cause:** The object does not exist, or the request requires authentication.
S3 evaluates CORS separately from access control. If the actual request would
return a 403, the preflight also returns 403 without CORS headers.

**Check:** Can the object be accessed without CORS (direct curl without Origin header)?
If it returns 403, fix the access control first, then retest CORS.

### Symptom: CORS headers present on preflight but missing on actual GET

**Cause:** Wildcard `*` in `AllowedOrigin` is not allowed when `AllowedHeader: *`
is also set AND the client sends `withCredentials: true`.

Browsers require `Access-Control-Allow-Origin` to be a specific origin (not `*`)
when the request includes credentials. S3 will not return a wildcard origin if
`AllowedOrigin` is `*` and the request sends credentials.

**Fix:** Change `AllowedOrigin` from `*` to the specific origin. Only specific origins
can be paired with credentialed requests.

### Symptom: ETag not accessible in JavaScript after upload

**Cause:** `ETag` is not in the `ExposeHeader` list of the CORS rule.
By default, only safe-listed response headers are accessible to JavaScript.
`ETag` is not safe-listed and must be explicitly exposed.

**Fix (manual-only):**
```xml
<ExposeHeader>ETag</ExposeHeader>
```

---

## AllowedOrigin Pattern Matching

- Exact match: `https://app.example.com` (recommended)
- Wildcard prefix: `https://*.example.com` (S3 supports one wildcard `*` per origin)
- Match-all: `*` (allows any origin; use only for truly public, unauthenticated content)

S3 does NOT support regex patterns in `AllowedOrigin`.

---

## Difference from Bucket Policy CORS

The S3 CORS configuration (set via `put-bucket-cors`) is separate from bucket policy.
CORS only affects browser-initiated cross-origin requests and adds HTTP headers.
It does NOT grant any permissions — access control is governed by IAM and bucket policy.

Common confusion: "I added CORS but still get 403" → CORS does not grant object access.
The user or public must still have `s3:GetObject` permission.

---

## Checking CORS Configuration

```bash
# manual-only: Get current CORS configuration
aws s3api get-bucket-cors --bucket <bucket>

# Test preflight directly
curl -v -X OPTIONS \
  -H "Origin: https://your-app.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Content-Type" \
  https://<bucket>.s3.<region>.amazonaws.com/<object>
```

---

## Safety Constraints

- Do not recommend `AllowedOrigin: *` unless the content is truly public
- `AllowedOrigin: *` combined with `AllowedHeader: *` breaks credentialed requests
- CORS changes must be tagged `manual-only`
- Verify access control (IAM/bucket policy) before diagnosing CORS — a 403 will suppress CORS headers
