# Case: Lambda Never Fires — Target Resource Policy Lacks S3 Allow

## Scenario
A bucket is configured with an `s3:ObjectCreated:*` notification targeting an
ingest Lambda. New objects upload successfully, but the Lambda is never invoked
and there is no error anywhere — S3 silently drops events when the target
rejects them. The Lambda's resource policy (`aws lambda get-policy`) only allows
API Gateway to invoke the function; it has no statement allowing
`s3.amazonaws.com` to `lambda:InvokeFunction`.

## What It Tests
- Identifies the root cause as a missing target resource-policy allow for S3,
  not a notification-rule/event-type/filter problem (the rule would fire).
- Recommends adding the `lambda:InvokeFunction` allow for principal
  `s3.amazonaws.com` scoped with `aws:SourceArn` to the source bucket.
- Confirmable offline with `scripts/notification_target_policy_validator.py`.
- Stays safe: no destructive or credential-exposing actions.

## Difficulty
medium
