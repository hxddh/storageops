# SigV4 Signature Process

AWS Signature Version 4 is the signing mechanism used by S3 and S3-compatible
services. Most `SignatureDoesNotMatch` errors trace to one of the following root causes.

## Signing Steps

1. **Create a canonical request:**
   ```
   CanonicalRequest =
     HTTPMethod + '\n' +
     CanonicalURI + '\n' +
     CanonicalQueryString + '\n' +
     CanonicalHeaders + '\n' +
     SignedHeaders + '\n' +
     HexEncode(Hash(RequestPayload))
   ```

2. **Create a string to sign:**
   ```
   StringToSign =
     'AWS4-HMAC-SHA256\n' +
     TimeStamp + '\n' +
     Date/Region/Service + '\n' +
     HexEncode(Hash(CanonicalRequest))
   ```

3. **Calculate the signing key:**
   ```
   kSecret  = "AWS4" + SecretKey
   kDate    = HMAC(kSecret, Date)
   kRegion  = HMAC(kDate, Region)
   kService = HMAC(kRegion, "s3")
   kSigning = HMAC(kService, "aws4_request")
   ```

4. **Calculate signature:**
   ```
   Signature = HexEncode(HMAC(kSigning, StringToSign))
   ```

5. **Add Authorization header:**
   ```
   Authorization: AWS4-HMAC-SHA256 Credential=AKID/Date/Region/s3/aws4_request,
   SignedHeaders=host;x-amz-content-sha256;x-amz-date,
   Signature=<Signature>
   ```

## Common Failure Causes

### Clock Skew
- AWS SigV4 allows ±15 minutes of clock skew.
- If the client's system clock differs from the server's clock by more than 15 minutes, the signature will fail.
- **Check:** `date -u` vs expected server time.
- **Fix:** Sync the client clock via NTP.

### Incorrect Region
- The signing region must match the region of the endpoint.
- Default region inference may be wrong for S3-compatible providers.
- **Check:** Verify `--region` or `AWS_DEFAULT_REGION`.

### Endpoint / Host Header Mismatch
- The `Host` header in the canonical request must match the actual endpoint.
- Virtual-hosted-style: `Host: <bucket>.<endpoint>`
- Path-style: `Host: <endpoint>`
- If the signing uses path-style but the HTTP request uses virtual-hosted-style (or vice versa), the signature will fail.

### Payload Hash (UNSIGNED-PAYLOAD)
- Some tools use `UNSIGNED-PAYLOAD` to avoid hashing large payloads.
- This must be consistent between the canonical request and the actual request.
- `x-amz-content-sha256: UNSIGNED-PAYLOAD` in the signed headers.

### Signed Headers Mismatch
- The headers included in SignedHeaders must exactly match the headers in CanonicalHeaders.
- Additional headers not in SignedHeaders will not break the signature, but missing signed headers will.

### Query Parameter Auth (Pre-signed URLs)
- Pre-signed URLs use SigV4 with query parameters instead of Authorization header.
- Expiration time is embedded; expired URLs fail.
- Query parameter encoding must be exact (URL-encoding of query params).

## Debugging SigV4 Errors

The `SignatureDoesNotMatch` response typically includes:
```xml
<Error>
  <Code>SignatureDoesNotMatch</Code>
  <Message>The request signature we calculated does not match...</Message>
  <StringToSign>...</StringToSign>
  <CanonicalRequest>...</CanonicalRequest>
</Error>
```

Compare the provided StringToSign and CanonicalRequest with what the client
expected to send. Any discrepancy is the root cause.
