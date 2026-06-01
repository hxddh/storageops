# How to Enable Access Logging

Quick setup guides for enabling server access logging on each object storage provider.

## AWS S3

1. Create a target bucket for logs (e.g., `my-logs-bucket`). Use a separate bucket — never log to the same bucket being logged.
2. Grant the S3 Log Delivery group write access. Add this bucket policy to the target bucket:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "logging.s3.amazonaws.com"},
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::my-logs-bucket/*",
      "Condition": {
        "StringEquals": {"aws:SourceAccount": "123456789012"}
      }
    }
  ]
}
```
3. Enable logging on the source bucket:
   - AWS Console → S3 → bucket → Properties → Server access logging → Enable
   - Set target bucket = `my-logs-bucket`, prefix = `logs/` (optional)
   - Or via CLI: `aws s3api put-bucket-logging --bucket my-source-bucket --bucket-logging-status '{"LoggingEnabled":{"TargetBucket":"my-logs-bucket","TargetPrefix":"logs/"}}'`

Logs appear in the target bucket within a few hours. Format: `logs/YYYY-MM-DD-HH-MM-SS-<hash>`.

## AWS CloudTrail (Data Events)

For API-level logging (all S3 operations including object-level):
1. CloudTrail → Trails → Create trail
2. Enable for all regions, create or select an S3 bucket for delivery
3. Under "Data events", select "S3" and choose "All current and future S3 buckets"
4. Optionally send to CloudWatch Logs for real-time analysis

CloudTrail delivers events within 15 minutes (typically 5 minutes).

## BOS (百度云)

1. Open BOS Console → bucket → Logging Settings
2. Enable logging, select a target bucket for log storage
3. Choose log prefix (optional)
4. Logs are delivered in tab-separated format

## COS (腾讯云)

1. COS Console → bucket → Log Management → Logging
2. Enable logging, select target bucket
3. Optionally specify path prefix and log file prefix
4. Logs are delivered in JSON format

## OSS (阿里云)

1. OSS Console → bucket → Logging → Settings
2. Enable logging, select target bucket for log storage
3. Specify log file prefix (optional)
4. Logs are delivered in CSV-like space-delimited format

## Common Issues

- **Logs not appearing**: S3 access logs take up to 24 hours on first enable. Subsequent logs appear hourly.
- **Log delivery failure**: Check that the target bucket exists, is in the same region, and the bucket policy allows the logging service principal.
- **Cost**: Access logging generates PUT requests to the target bucket (charged at standard PUT rates). For high-traffic buckets, logs can be significant in volume.
