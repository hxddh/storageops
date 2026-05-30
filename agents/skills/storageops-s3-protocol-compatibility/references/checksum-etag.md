# ETag and Checksum Semantics

## ETag Formats

### Single PUT Upload
- **AWS S3:** ETag is the hex-encoded MD5 hash of the object content.
  Example: `"d41d8cd98f00b204e9800998ecf8427e"`
- **Note:** If SSE (Server-Side Encryption) is used, the ETag is NOT the MD5.

### Multipart Upload
- **AWS S3:** ETag is the hex-encoded MD5 of the concatenated binary MD5 hashes of each part, followed by `-<part count>`.
  Example: `"a1b2c3d4e5f6...-4"` for a 4-part upload.
- **This is NOT the MD5 of the full object content.**

### CopyObject
- ETag of the copy may differ from the source object's ETag.
- Some providers preserve the source ETag; AWS S3 does not (unless SSE-C).

## Content-MD5

- **Header:** `Content-MD5: <base64 of binary MD5>`
- AWS S3 validates Content-MD5 on PUT and returns an error if it doesn't match.
- Some S3-compatible providers ignore Content-MD5.
- Some providers REQUIRE Content-MD5 for integrity checking.

## Checksum Algorithms (AWS S3 newer)

- **CRC32C:** `x-amz-checksum-crc32c`
- **CRC32:** `x-amz-checksum-crc32`
- **SHA1:** `x-amz-checksum-sha1`
- **SHA256:** `x-amz-checksum-sha256`
- Most S3-compatible providers do NOT support these yet.

## rclone Size Diff / Corrupted on Transfer

These errors typically indicate:

1. **ETag mismatch after transfer:** The source ETag does not match the destination ETag.
   - Single-part copy: ETags should match if no SSE.
   - Multipart copy: ETags will differ (different part boundaries).
   - Some providers change ETag format (with/without quotes, different hashing).

2. **Size diff:** Source and destination object sizes differ.
   - Content-MD5 mismatch during PUT.
   - Truncated upload.
   - Encoding transformation by middleware/proxy.

3. **Corrupted on transfer:** Content-MD5 validation failed.
   - Bit flip during transmission.
   - Client-side memory corruption.
   - Proxy transformation.

## ETag with SSE

- **SSE-S3:** ETag is NOT the MD5 of plaintext.
- **SSE-C:** ETag IS the MD5 of the encrypted object (with customer key).
- **SSE-KMS:** ETag is NOT the MD5.
- If you're using SSE, you cannot verify integrity by computing the file MD5 and comparing to ETag.

## Debugging Checklist

1. Was the object uploaded via single PUT or multipart?
2. Is SSE involved?
3. Does the ETag format match expectations (hex-encoded MD5, or MD5-MD5-...-N)?
4. Compare Content-MD5 in request vs actual file MD5.
5. Check for proxy or middleware that may transform content.
