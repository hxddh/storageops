# S3 Server Access Logs — Field Reference

Standard S3 Server Access Log format. One log entry per line, space-delimited.

## Field Order

| # | Field | Description | Example |
|---|-------|-------------|---------|
| 1 | BucketOwner | AWS account ID of bucket owner | `123456789012` |
| 2 | Bucket | Bucket name | `my-bucket` |
| 3 | Time | Request timestamp `[DD/Mon/YYYY:HH:MM:SS +TZ]` | `[30/May/2026:14:32:01 +0000]` |
| 4 | RemoteIP | Requester IP address | `203.0.113.45` |
| 5 | Requester | AWS ARN or authenticated user ID. `-` for anonymous. | `arn:aws:iam::123456789012:user/jane` |
| 6 | RequestID | S3-generated request ID | `3E57427F33A59F07` |
| 7 | Operation | `REST.HTTP_METHOD.OBJECT` or `WEBSITE.HTTP_METHOD.OBJECT` | `REST.GET.OBJECT` |
| 8 | Key | Object key, URL-encoded. `-` for bucket-level operations. | `images%2Fphoto.jpg` |
| 9 | RequestURI | Full request URI including query string | `GET /images/photo.jpg HTTP/1.1` |
| 10 | HTTPStatus | HTTP status code | `200`, `403`, `429` |
| 11 | ErrorCode | S3 error code. `-` if no error. | `AccessDenied`, `SlowDown` |
| 12 | BytesSent | Bytes sent in response body | `1048576` |
| 13 | ObjectSize | Object size in bytes | `1048576` |
| 14 | TotalTime | Total request time in ms | `45` |
| 15 | TurnaroundTime | Server processing time in ms | `12` |
| 16 | Referer | HTTP Referer header. `-` if none. | `https://example.com` |
| 17 | UserAgent | HTTP User-Agent header (double-quoted) | `"aws-sdk-java/2.1.0"` |
| 18 | VersionId | Object version ID. `-` if versioning disabled. | `3HL4kqYK8MgA7AJzC` |
| 19 | HostId | S3 host ID | `s9tBq...` |
| 20 | SignatureVersion | SigV2 or SigV4 | `SigV4` |
| 21 | CipherSuite | TLS cipher suite (for SSL) | `ECDHE-RSA-AES128-GCM-SHA256` |
| 22 | AuthenticationType | Auth method | `AuthHeader` |
| 23 | HostHeader | Host header from request | `my-bucket.s3.amazonaws.com` |
| 24 | TLSVersion | TLS version | `TLSv1.2` |
| 25 | AccessPointARN | S3 Access Point ARN (if used). `-` if none. | `arn:aws:s3:us-east-1:123:accesspoint/my-ap` |

## Key Operations (Field 7)

| Operation | Meaning |
|-----------|---------|
| `REST.GET.OBJECT` | Object download |
| `REST.PUT.OBJECT` | Object upload |
| `REST.DELETE.OBJECT` | Object deletion |
| `REST.HEAD.OBJECT` | Object metadata check |
| `REST.GET.BUCKET` | List objects (LIST) |
| `REST.COPY.OBJECT` | Copy object |
| `REST.POST.MULTIPLE_OBJECT_DELETE` | Batch delete |
| `REST.GET.UPLOAD` | List multipart uploads |
| `REST.GET.ACCELERATE` | Transfer acceleration config |
| `WEBSITE.GET.OBJECT` | Static website GET |
| `S3.CREATE.BUCKET` | Bucket creation |

## Common Anomaly Patterns

1. **Anonymous requests (Requester=`-`) with 200**: Public bucket serving content — verify this is intentional.
2. **Requests with empty key (Key=`-`)**: Bucket-level operations (LIST, HEAD bucket). High count = client listing excessively.
3. **Consistently high TotalTime vs TurnaroundTime**: Network latency issue, not server-side.
4. **SignatureVersion=SigV2**: Old client. SigV2 deprecated in new S3 regions (2019+).
