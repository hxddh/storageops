# Provider-Specific Log Format Differences

> **⚠️ Unverified:** the BOS/COS rows below have not been confirmed against vendor
> docs and **contradict** both `SKILL.md` Step 1 (which says BOS/COS are CSV) and
> `scripts/parse_access_log.py` (which parses both as CSV). Treat the BOS/COS
> format details here as provisional until verified against a real sample; the
> parser deliberately refuses to emit results when its expected columns are absent.

## Comparison Table

| Provider | Format | Delimiter | Encoding | Timestamp Format | Key Encoding |
|----------|--------|-----------|----------|-----------------|--------------|
| AWS S3 | Plain text | Space | URL-encoded | `[DD/Mon/YYYY:HH:MM:SS +TZ]` | URL-encoded (`%2F` for `/`) |
| BOS | Plain text | Tab (`\t`) | Raw | `YYYY-MM-DD HH:MM:SS` | Raw |
| COS | JSON | N/A | UTF-8 | ISO 8601 | Raw |
| OSS | Plain text | Space | Raw | `DD/Mon/YYYY:HH:MM:SS +TZ` | Raw |

## BOS (百度云) Format

Tab-separated, one request per line:
```
2026-05-30 14:32:01	203.0.113.45	my-bucket	images/photo.jpg	GET	200	1048576	1048576	-	"aws-sdk-java/2.1.0"	3E57427F33A59F07	arn:aws:iam::user/jane
```

Field order: `time \t remote_ip \t bucket \t key \t operation \t http_status \t bytes_sent \t object_size \t referer \t user_agent \t request_id \t requester`

Notes:
- Timestamps are local time (UTC+8), not UTC
- Keys are not URL-encoded (raw path)
- No SignatureVersion or TLS version fields
- Referer and user-agent may be `-` if not present

## COS (腾讯云) Format

JSON array, one JSON object per request:
```json
[
  {
    "eventTime": "2026-05-30T14:32:01Z",
    "bucketName": "my-bucket-1250000000",
    "objectName": "images/photo.jpg",
    "reqMethod": "GET",
    "resHttpCode": 200,
    "resTotalSize": 1048576,
    "objectSize": 1048576,
    "referer": "https://example.com",
    "userAgent": "aws-sdk-java/2.1.0",
    "requestId": "NjkzY...",
    "accountId": "100012345678",
    "reservedField": "203.0.113.45"
  }
]
```

Notes:
- Field names differ from S3 (e.g., `objectName` not `key`, `reqMethod` not `operation`)
- Bucket name includes APPID suffix (`-1250000000`)
- `reservedField` contains source IP
- Timestamps use ISO 8601 with `Z` suffix

## OSS (阿里云) Format

Space-delimited, similar to S3 but fewer fields:
```
2026-05-30 14:32:01 203.0.113.45  GET  images/photo.jpg  200  1048576  1048576  0  45  https://example.com  "aws-sdk-java/2.1.0"  3E57427F33A59F07  -  arn:aws:iam::user/jane  my-bucket
```

Field order: `date time remote_ip operation key http_status bytes_sent object_size request_time referer user_agent request_id error_code requester bucket`

Notes:
- Timestamps are local time
- Fewer fields than S3 (no SignatureVersion, no TLS, no TurnaroundTime)
- Referer and user-agent use same format as S3
- Error code field may be empty or `-`
