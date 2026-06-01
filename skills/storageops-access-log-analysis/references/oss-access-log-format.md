# OSS Access Log Format (Alibaba Cloud Object Storage Service)

## Overview
OSS offers real-time log query via the OSS console (Log Service integration) and traditional log delivery to a target bucket. Real-time logs are JSON. Traditional delivery is tab-separated.

## Real-Time Log (JSON)

```json
{
  "accessId": "LTAI4G...",
  "bucket": "my-bucket",
  "bucketLocation": "oss-cn-hangzhou",
  "clientIp": "203.0.113.45",
  "deltaDataSize": 1048576,
  "errorCode": "AccessDenied",
  "httpStatus": 403,
  "object": "path/to/object.jpg",
  "objectSize": 1048576,
  "operation": "GetObject",
  "referer": "https://example.com/",
  "requestId": "5F5B4C12A3...",
  "requestUri": "GET /path/to/object.jpg HTTP/1.1",
  "responseSize": 0,
  "syncRequest": true,
  "time": "2025-02-06T14:23:00Z",
  "userAgent": "aliyun-sdk-java/3.16.0"
}
```

## Legacy Delivery Log (Tab-Separated)

Fields (in order): `bucket_owner`, `bucket`, `time`, `remote_ip`, `requester`, `request_id`, `operation`, `key`, `request_uri`, `http_status`, `error_code`, `bytes_sent`, `object_size`, `total_time`, `turnaround_time`, `referer`, `user_agent`, `version_id`

## Key Differences from S3

- Real-time logs: JSON format, queried via Log Service (SQL-like syntax)
- Legacy format: Tab-separated, similar to S3 but fewer fields
- No Requester field: Uses `accessId` (RAM user access key)
- `deltaDataSize`: Data transferred (useful for cost analysis)

## Common OSS Error Codes

| Error Code | Meaning |
|------------|---------|
| `AccessDenied` | RAM policy or Bucket Policy denies |
| `NoSuchKey` | Object not found |
| `NoSuchBucket` | Bucket not found |
| `SignatureDoesNotMatch` | AK/SK or STS token issue |
| `RequestTimeTooSkewed` | Clock skew > 15 min |
| `InvalidAccessKeyId` | Access key doesn't exist or is disabled |
| `BucketAlreadyExists` | Bucket name already taken |
| `CallbackFailed` | Upload callback to user server failed |

## Log Service Query Examples

```
-- Top 10 IPs by error count
* | SELECT clientIp, count(*) AS cnt WHERE httpStatus >= 400
    GROUP BY clientIp ORDER BY cnt DESC LIMIT 10

-- 403 error spike detection (last 1 hour)
* | SELECT date_trunc('minute', __time__) AS t, count(*) AS cnt
    WHERE errorCode = 'AccessDenied' GROUP BY t ORDER BY t

-- Traffic by requester (cost attribution)
* | SELECT accessId, sum(deltaDataSize) AS total_bytes
    GROUP BY accessId ORDER BY total_bytes DESC
```
