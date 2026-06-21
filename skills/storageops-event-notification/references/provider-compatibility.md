# Event Notification Provider Compatibility

## When to read
Use when the bucket is on a non-AWS provider (Baidu BOS, Alibaba OSS, Tencent COS,
Huawei OBS, MinIO) and events are not delivered. The S3 *API* is compatible, but
event notification is **not** a wire-protocol feature — it is a provider-native
subsystem, so AWS assumptions (the `s3.amazonaws.com` principal, Lambda/SQS/SNS
targets) do not carry over.

> **AWS-specific tooling.** `notification_config_analyzer.py` and
> `notification_target_policy_validator.py` model AWS S3→Lambda/SQS/SNS and emit
> `"model": "aws"`. They do **not** validate the providers below — use them only for
> AWS, and verify non-AWS specifics against the provider's docs.

## What differs by provider (orient, then verify)
- **Targets are provider-native, not SNS/SQS/Lambda.** Typically the event goes to
  the provider's own function-compute and message-queue services rather than AWS
  ones (e.g. a serverless-function target and a managed message queue). The *target
  permission model* is the provider's, not an AWS resource policy with
  `s3.amazonaws.com`.
- **Event taxonomies differ.** Object-created / object-removed style events exist on
  most providers, but the exact event-type strings, the multipart-completion event,
  and delete-marker semantics are provider-specific — confirm the names against the
  provider's docs rather than assuming `s3:ObjectCreated:*`.
- **Filter & retry semantics differ.** Prefix/suffix filter rules, overlap handling,
  and delivery-retry / dead-letter guarantees are not guaranteed to match AWS.

## Diagnostic approach on a non-AWS provider
1. Identify the provider first (endpoint host / console naming).
2. Split the two legs as always: does the rule *match* the object (event type +
   filter), and does the *target* accept delivery (the provider's own permission
   model)?
3. Check the target's native permission/binding in the provider console/API — not an
   AWS-style resource policy.
4. Confirm the event-type string and filter semantics against the provider's docs.

## Routing
- Target permission / rule-match → stay in this skill (but use the provider's model,
  not the AWS validators).
- Endpoint / signature / region errors → `storageops-s3-protocol-compatibility` or
  `storageops-network-endpoint-access`.
