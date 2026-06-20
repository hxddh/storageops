# SNS Integration

## When to read
Use when an SNS topic does not publish object events, or it publishes but
subscribers do not receive them. First confirm the bucket rule matches the object
(`notification-configuration.md`); this file covers the SNS *target* side. SNS is
usually a fan-out hop in front of SQS/Lambda/HTTP — split "S3→SNS" from
"SNS→subscriber".

## Mental model
Two delivery legs, each with its own failure mode:
- **S3 → SNS:** S3 calls `sns:Publish` as `s3.amazonaws.com`. The **topic policy**
  must allow it, or S3 drops the event silently.
- **SNS → subscriber:** even if publishing succeeds, the subscriber may not get it
  because the subscription is unconfirmed, a filter policy excludes the message, or
  the downstream resource policy rejects SNS.

## Checks (in order)
1. **Topic policy allows S3 to publish.** Statement: `Action: SNS:Publish`,
   `Principal.Service: s3.amazonaws.com`, `Resource` = topic ARN, `Condition`
   `aws:SourceArn` = bucket ARN.
2. **Subscription is confirmed.** A `PendingConfirmation` subscription receives
   nothing. HTTP/email subscriptions must complete the confirmation handshake.
3. **Filter policy.** A subscription filter policy that does not match the message
   attributes silently drops it. S3→SNS messages carry limited attributes — a
   filter expecting custom attributes will exclude every event.
4. **Downstream resource policy.** For SNS→SQS, the queue policy must allow
   `sqs:SendMessage` from `sns.amazonaws.com`; for SNS→Lambda, the function policy
   must allow invoke from `sns.amazonaws.com`. These are separate from the S3 grants.
5. **KMS.** If the topic is SSE-KMS, the key policy must allow the S3 service
   principal (`kms:GenerateDataKey`, `kms:Decrypt`); the AWS-managed SNS key cannot
   be shared with S3.

## How to confirm
```bash
aws sns get-topic-attributes --topic-arn <arn>          # Policy, KmsMasterKeyId
aws sns list-subscriptions-by-topic --topic-arn <arn>   # confirm SubscriptionArn != PendingConfirmation
aws sns get-subscription-attributes --subscription-arn <arn>  # FilterPolicy
```
Run `python3 scripts/notification_target_policy_validator.py --file <policy.json>
--target-type sns --source-bucket-arn arn:aws:s3:::<bucket>` to decide
deterministically whether the topic policy permits S3 delivery.

## Caveats / verification status
- AWS-verified. Provider equivalents (e.g. COS+CMQ/TDMQ) differ — verify against
  the provider's docs.
