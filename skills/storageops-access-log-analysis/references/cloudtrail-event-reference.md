# CloudTrail Event Reference

## data event

S3 Data Events (object-level API calls). Requires CloudTrail data events enabled.

| Field | Description | Example |
|-------|-------------|---------|
| eventVersion | Event format version | `1.09` |
| eventTime | ISO 8601 timestamp | `2026-05-30T14:32:01Z` |
| eventSource | Always `s3.amazonaws.com` for S3 | `s3.amazonaws.com` |
| eventName | API operation name | `GetObject`, `PutObject`, `DeleteObject` |
| sourceIPAddress | Requester IP | `203.0.113.45` |
| userAgent | Client user agent | `aws-sdk-java/2.1.0` |
| requestParameters | Object key, bucket name, version | `{"bucketName":"my-bucket","key":"photo.jpg"}` |
| responseElements | Response details (e.g., ETag, version ID) | `{"x-amz-request-id":"3E57427F","x-amz-id-2":"..."}` |
| errorCode | S3 error code if request failed | `AccessDenied`, `NoSuchKey` |
| errorMessage | Human-readable error | `Access Denied` |
| userIdentity | Type, ARN, accountId, principalId | IAM user, role, or root |
| resources | List of resources accessed (bucket ARN, object ARN) | `arn:aws:s3:::my-bucket` |
| requestID | S3 request ID | `3E57427F33A59F07` |

## Management Events

S3 Management Events (bucket-level operations — always logged by CloudTrail):

| eventName | Operation |
|-----------|-----------|
| CreateBucket | Bucket creation |
| DeleteBucket | Bucket deletion |
| PutBucketPolicy | Bucket policy change |
| PutBucketAcl | Bucket ACL change |
| PutBucketLogging | Enable/change access logging |
| PutBucketVersioning | Enable/suspend versioning |
| PutBucketEncryption | Set default encryption |
| PutPublicAccessBlock | Change public access block settings |

## Reading CloudTrail for Diagnosis

1. **Filter by errorCode**: `errorCode IS NOT NULL` → all failed requests
2. **Filter by eventName + bucket**: `eventName=PutObject AND requestParameters.bucketName=my-bucket`
3. **Group by userIdentity.arn**: Who is making the requests?
4. **Group by sourceIPAddress**: Where are requests coming from?

## Common Patterns

| Pattern | Significance |
|---------|-------------|
| Multiple GetObject with 403 from non-VPC IP | Possible public access leak or enumeration |
| PutBucketPolicy followed by GetObject spike from new IP | Policy change enabled new access |
| DeleteObject from unexpected userIdentity | Potential compromise |
| PutObject with unusual userAgent (non-SDK) | Direct API access — check if authorized |
