---
name: storageops-event-notification
description: >
  Diagnose S3 event notification failures: Lambda not triggered, SQS queue
  not receiving events, SNS topic not publishing, EventBridge events missing.
  Covers notification configuration, IAM permissions chaining, event type
  filtering, prefix/suffix filters, Lambda concurrency, and event delivery
  latency. Use when user expects events from S3 but targets aren't receiving them.
maturity: stable
mode: light_heavy
estimated_tokens: 1300
trigger_keywords:
  - event notification
  - Lambda not triggered
  - SQS not receiving
  - SNS notification
  - EventBridge
  - s3:ObjectCreated
  - s3:ObjectRemoved
  - notification configuration
  - event missing
  - CloudTrail
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# S3 Event Notification Diagnosis

S3 events follow a chain: Object action → Notification rule match (event type + prefix/suffix filter) → IAM permissions → Target (Lambda/SQS/SNS/EventBridge). A break at any link stops delivery.

## Decision Tree

```
Event not delivered →
  ├─ No events at all? → Configuration chain (Step 1-3)
  │   ├─ Notification config exists? → Check bucket notification settings
  │   ├─ Event type matches? → ObjectCreated:Put vs ObjectCreated:CompleteMultipartUpload
  │   └─ Prefix/suffix filter correct? → Most common: wrong prefix or missing suffix
  ├─ Some events missing (intermittent)? → Delivery chain (Step 4-6)
  │   ├─ Lambda concurrency limit? → Throttled invocations (Step 5)
  │   ├─ SQS message size limit? → Event >256KB gets dropped
  │   └─ Target has resource policy allowing S3? → Often overlooked (Step 4)
  └─ Events arriving but wrong format? → EventBridge vs direct notification
```

## Workflow

### Step 1: Verify Notification Configuration Exists
Check `PUT Bucket notification` configuration on the source bucket. No config = no events. Simple but commonly overlooked after bucket recreation.

### Step 2: Check Event Type Matching
- `s3:ObjectCreated:Put` — fires on PUT (single-shot upload)
- `s3:ObjectCreated:CompleteMultipartUpload` — fires on multipart completion
- `s3:ObjectCreated:*` — fires on ANY object creation
- `s3:ObjectRemoved:*` — fires on delete/multi-delete
**Common mistake**: Expecting `ObjectCreated:*` to fire on multipart completion when only `ObjectCreated:Put` is configured.

### Step 3: Check Prefix/Suffix Filters
Notification rules support prefix and suffix filtering. If configured, events only fire for matching objects. Empty/missing filter = match all.

### Step 4: IAM Permission Chain
S3 needs `lambda:InvokeFunction` to call Lambda, or `sqs:SendMessage` to send to SQS. But ALSO:
- **Lambda**: Resource-based policy must allow `s3.amazonaws.com` as principal + `lambda:InvokeFunction` + source bucket ARN
- **SQS**: Queue policy must allow S3 principal `s3.amazonaws.com` + `sqs:SendMessage`
- **SNS**: Topic policy must allow S3 principal + `sns:Publish`

### Step 5: Lambda Concurrency
If Lambda is throttled (`TooManyRequestsException`), events are retried but may ultimately be dropped if backlog exceeds retention. Check Lambda reserved concurrency and CloudWatch throttle metrics.

### Step 6: Delivery Reliability
S3 event notifications are at-least-once delivery, but NOT guaranteed. For critical workflows, enable S3 event notification to SQS as a durable buffer, then have Lambda consume from SQS.

## Output Format

```markdown
# Diagnosis: [one-line]
**Failure point**: no-config | event-type-mismatch | filter-mismatch | iam-gap | lambda-throttle | target-policy
**Confidence**: high | medium | low

## Evidence
- Bucket notification config: [present? event types? filters?]
- Target type: [Lambda/SQS/SNS/EventBridge]
- Error logs: [from CloudWatch/SQS DLQ]

## Permission Chain Trace
1. Notification config: [OK/missing — details]
2. Target resource policy: [OK/missing — check principal:s3.amazonaws.com]
3. Lambda concurrency: [OK/throttled — check metrics]

## Recommendations
1. **[fix]** (manual-only)
```

## Examples

### Example 1: Lambda not triggered on multipart upload
**Input**: Lambda processes new objects. Works for small files, but larger files (>5MB multipart) don't trigger.
**Diagnosis**: Event type is `s3:ObjectCreated:Put` only. Multipart uploads emit `s3:ObjectCreated:CompleteMultipartUpload`, not `Put`.
**Recommendation**: Add `s3:ObjectCreated:CompleteMultipartUpload` to notification event types. Or use `s3:ObjectCreated:*`.

### Example 2: SQS not receiving — missing queue policy
**Input**: S3 notification configured to send to SQS, but queue remains empty.
**Diagnosis**: SQS queue policy missing — S3 principal not authorized. S3 silently drops events if target doesn't have proper permissions (no error returned to caller).
**Recommendation**: Add SQS queue policy: Principal `s3.amazonaws.com`, Action `sqs:SendMessage`, Condition `ArnLike: {aws:SourceArn: arn:aws:s3:::source-bucket}`.

### Example 3: Intermittent event loss under load
**Input**: Events delivered normally until high traffic. Under load, some events never arrive.
**Diagnosis**: Lambda concurrency limit reached. S3 retries events, but if Lambda stays throttled, events eventually expire.
**Recommendation**: Increase Lambda reserved concurrency. Or fan-out: S3→SNS→SQS (subscription filter)→Lambda. SQS acts as durable buffer.

## References
- `references/notification-configuration.md` — Full notification schema, event types
- `references/lambda-integration.md` — Lambda resource policy, concurrency, DLQ
- `references/sqs-integration.md` — SQS queue policy, message attributes
- `references/sns-integration.md` — SNS topic policy, subscription filters
- `references/provider-compatibility.md` — Non-AWS event notification (BOS/OSS/COS event triggers)
