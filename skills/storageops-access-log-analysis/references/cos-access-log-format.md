# COS Access Log Format (Tencent Cloud Object Storage)

## Overview
COS supports log delivery to a designated bucket. Enable via COS Console → Bucket → Log Management. Logs are CSV format with headers in the first row. Delivery delay: typically 1-3 hours.

## Log Schema (CSV)

| Field | Description | Example |
|-------|-------------|---------|
| eventTime | Request timestamp (UTC) | `2025-02-06 14:23:00` |
| eventSource | COS domain | `my-bucket-1250000000.cos.ap-guangzhou.myqcloud.com` |
| eventName | API operation | `GETObject` |
| remoteIp | Requester IP | `203.0.113.45` |
| userAccessKeyId | SecretId of requester | `AKIDxxxx...` (last 8 chars) |
| reqPath | Object key with leading `/` | `/path/to/object.jpg` |
| reqMethod | HTTP method | `GET` |
| userAgent | HTTP User-Agent | `cos-python-sdk-v5.1.9` |
| resHttpCode | HTTP status code | `200` |
| resErrorCode | COS error code or `-` | `AccessDenied` |
| resErrorMsg | Error message | `Access Denied.` |
| resBytesSent | Response bytes | `1048576` |
| resTotalTime | Total time (ms) | `45` |
| logSourceType | USER (console) or CDN | `USER` |
| storageClass | Object storage class | `STANDARD` |
| accountId | Tencent Cloud account ID | `100012345678` |
| resTurnAroundTime | Server processing time (ms) | `12` |
| requester | Full SecretId (visible to bucket owner) | `AKIDxxxx...` |
| requestUri | Full request URI | `GET /path/to/object.jpg` |
| objectSize | Object size (bytes) | `1048576` |

## Key Differences from S3

- CSV format with header row
- Timestamp in `YYYY-MM-DD HH:MM:SS` (space separator, not T)
- `userAccessKeyId`: SecretId partial (masked); `requester`: full SecretId
- `logSourceType`: distinguishes CDN from direct USER access
- Fields `eventSource` and `reqPath` are separate (vs S3's combined Host Header + Key)

## Common COS Error Codes

| Error Code | Meaning |
|------------|---------|
| `AccessDenied` | CAM policy or Bucket Policy denies |
| `NoSuchKey` | Object not found |
| `NoSuchBucket` | Bucket not found |
| `SignatureDoesNotMatch` | SecretId/SecretKey mismatch |
| `SlowDown` | Rate throttling |
| `InvalidAccessKeyId` | SecretId doesn't exist |
| `RequestTimeTooSkewed` | Clock skew issue |
| `ObjectLocked` | Object is WORM-locked |

## Query Tips

- `eventSource` reveals the CDN vs direct access ratio
- `storageClass` shows access patterns by storage tier
- `logSourceType=CDN` entries may have different remoteIp (CDN edge node IP)
