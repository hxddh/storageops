# BOS Access Log Format (Baidu Object Storage)

## Overview
BOS supports access logging via bucket-level configuration. Logs are delivered as CSV files to a designated logging bucket/prefix. Enable via BOS Console → Bucket → Logging.

## Log Schema

| Field | Description | Example |
|-------|-------------|---------|
| time | Request timestamp (UTC) | `2025-02-06T14:23:00Z` |
| remote_ip | Requester IP address | `203.0.113.45` |
| requester | Baidu account ID | `user-abc123def456` |
| request_id | BOS-generated request ID | `f4a8b2c1-d3e5-6789-abcd-ef0123456789` |
| operation | API operation | `GetObject` |
| bucket | Bucket name | `my-bucket` |
| key | Object key | `/path/to/object.jpg` |
| request_uri | Full request URI | `GET /path/to/object.jpg` |
| http_status | HTTP status code | `200` |
| error_code | BOS error code or `-` | `AccessDenied` |
| bytes_sent | Response size (bytes) | `1048576` |
| object_size | Object size (bytes) | `1048576` |
| total_time_ms | Total request time | `45` |
| referer | HTTP Referer or `-` | `https://example.com/` |
| user_agent | HTTP User-Agent or `-` | `bce-sdk-python/2.0.1` |
| log_delivery_time | When log was delivered | `2025-02-06T15:23:00Z` |

## Key Differences from S3

- CSV format (comma-separated) vs space-delimited
- Timestamp in ISO 8601 vs Apache CLF format
- `requester` is Baidu account ID (not IAM ARN)
- `operation` uses simpler names: `GetObject` vs `REST.GET.OBJECT`

## Common BOS Error Codes

| Error Code | Meaning |
|------------|---------|
| `AccessDenied` | Authorization failed (wrong AK/SK, expired token) |
| `NoSuchKey` | Object does not exist |
| `NoSuchBucket` | Bucket does not exist |
| `SignatureDoesNotMatch` | AK/SK mismatch or wrong signing region |
| `RequestTimeout` | Request took too long |
| `SlowDown` | Rate limited |
| `ServiceUnavailable` | BOS internal error (retry) |
