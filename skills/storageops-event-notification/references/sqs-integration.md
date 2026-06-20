# SQS Integration

## When to read
Use when an SQS queue stays empty despite object events that should match. First
confirm the bucket rule matches the object (`notification-configuration.md`); this
file covers the SQS *target* side.

## Mental model
S3 delivers by calling `sqs:SendMessage` as principal `s3.amazonaws.com`. The
**queue policy** (a resource policy on the queue) must allow that. If it does not,
S3 drops the event with no error to the writer. If SSE is enabled on the queue,
the **KMS key policy** must also let the S3 service principal use the key, or the
send fails after the queue policy passes.

## Checks (in order)
1. **Queue policy allows S3 to send.** Statement: `Action: sqs:SendMessage`,
   `Principal.Service: s3.amazonaws.com` (or `Principal: *` with a SourceArn
   condition), `Resource` = the queue ARN, and `Condition` `aws:SourceArn` = the
   bucket ARN. The console wizard adds this; IaC often omits it.
2. **Queue ARN, region, and account are correct** and match the configured
   destination. A cross-region queue is rejected at configuration time.
3. **SSE-KMS key policy.** If the queue uses a customer-managed KMS key, the key
   policy must allow `kms:GenerateDataKey` and `kms:Decrypt` for
   `s3.amazonaws.com`. SSE with the AWS-managed `alias/aws/sqs` key cannot be
   shared with S3 — use a customer-managed key for S3→SQS with SSE.
4. **FIFO queues are not valid S3 targets** — S3 delivers only to standard queues.
5. **Delivered-but-drained.** If messages arrive but the queue looks empty, a
   consumer or a short retention / aggressive redrive-to-DLQ may be removing them
   first. Check `ApproximateNumberOfMessages`, DLQ depth, and retention.

## How to confirm
```bash
aws sqs get-queue-attributes --queue-url <url> \
  --attribute-names Policy KmsMasterKeyId ApproximateNumberOfMessages RedrivePolicy
# If KMS is set, inspect the key policy for the s3.amazonaws.com grant:
aws kms get-key-policy --key-id <id> --policy-name default
```
Run `python3 scripts/notification_target_policy_validator.py --file <policy.json>
--target-type sqs --source-bucket-arn arn:aws:s3:::<bucket>` to decide
deterministically whether the queue policy permits S3 delivery.

## Caveats / verification status
- AWS-verified. COS/OSS message-queue targets use a different permission model —
  verify against the provider's docs.
