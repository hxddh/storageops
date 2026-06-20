# Lambda Integration

## When to read
Use when the notification target is a Lambda function and the function is not
invoked (or is invoked but the user thinks it is not). First confirm the bucket
rule actually matches the object (`notification-configuration.md`); this file
covers the Lambda *target* side.

## Mental model
S3 invokes Lambda **asynchronously**. Two independent things must hold: (1) the
function's **resource policy** must allow `lambda:InvokeFunction` for principal
`s3.amazonaws.com` scoped to the source bucket, and (2) the async delivery must
actually succeed. If the resource policy is missing, S3 drops the event silently —
no error to the writer. If the policy is present but the function errors, the
event was delivered; the bug is in the function or its async retry/DLQ.

## Checks (in order)
1. **Resource policy allows S3 to invoke.** The statement needs
   `Action: lambda:InvokeFunction`, `Principal.Service: s3.amazonaws.com`, and a
   `Condition` `aws:SourceArn` = the bucket ARN (and often `aws:SourceAccount`).
   This is what `aws lambda add-permission` creates; the console "Add trigger"
   button adds it for you, but IaC (Terraform/CDK) often forgets it.
2. **SourceArn/SourceAccount actually match** the source bucket. A stale ARN from
   a recreated bucket, or a wrong account, silently blocks delivery.
3. **Region.** The function and the bucket notification must be in the same region.
4. **Delivered-but-failing vs never-delivered.** If CloudWatch shows invocations,
   delivery works — debug the function (timeout, unhandled exception, throttling).
   If there are zero invocations, it is the resource policy or the bucket rule.
5. **Async retries and DLQ.** Async invokes retry twice on function error, then
   drop unless an on-failure destination / DLQ is configured. A missing DLQ hides
   failures as "lost events".
6. **Reserved concurrency = 0** (or exhausted account concurrency) causes S3 async
   invokes to be throttled and eventually dropped.

## How to confirm
```bash
aws lambda get-policy --function-name <fn>            # the resource policy
aws lambda get-function-configuration --function-name <fn> \
  --query '{Region:FunctionArn, Concurrency:ReservedConcurrentExecutions, DLQ:DeadLetterConfig}'
# Invocations / errors / throttles over the window:
aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Invocations ...
```
Run `python3 scripts/notification_target_policy_validator.py --file <get-policy.json>
--target-type lambda --source-bucket-arn arn:aws:s3:::<bucket>` to decide
deterministically whether the resource policy permits S3 delivery.

## Caveats / verification status
- AWS-verified. Other providers' function-compute triggers (e.g. SCF for COS,
  Function Compute for OSS) use a different permission model — verify against the
  provider's docs; do not assume `lambda:InvokeFunction` semantics.
