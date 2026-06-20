# Summary

Category: event_notification
Route: storageops-event-notification
Confidence: 0.85
Root Cause Type: target_policy_missing_s3_invoke (missing_target_permission)

The bucket notification rule is correct — `s3:ObjectCreated:*` with no
prefix/suffix filter would fire for every uploaded object. The break is at the
target: the ingest Lambda's resource policy does not allow S3 to invoke it. The
only statement present allows `apigateway.amazonaws.com`; there is no allow for
principal `s3.amazonaws.com` to `lambda:InvokeFunction`. S3 silently drops the
event when the target rejects the invocation, which is why uploads succeed yet
the Lambda is never invoked and no error reaches the uploader. This is a
target permission problem, not an event-type, filter, or corruption issue.

# Key Evidence

- Notification rule: `s3:ObjectCreated:*` -> Lambda `ingest`, no prefix/suffix
  filter, so the rule would fire for the uploaded objects.
- The Lambda resource policy (`aws lambda get-policy` output) contains only an
  `apigateway.amazonaws.com` statement. It has NO statement with principal
  Service `s3.amazonaws.com` and Action `lambda:InvokeFunction`.
- `scripts/notification_target_policy_validator.py --file lambda-get-policy.json
  --target-type lambda --source-bucket-arn arn:aws:s3:::ingest-source` returns
  `policy_ok: false`, with `missing` listing the `s3.amazonaws.com`
  `lambda:InvokeFunction` allow — confirming the resource policy is the gap.
- Uploads (PutObject) succeed and objects appear in the bucket, but Lambda
  CloudWatch Logs show zero invocations and no error is returned — the signature
  of a silently dropped event due to a missing target permission.

# Remediation

- Add an `Allow` statement to the Lambda resource policy granting
  `lambda:InvokeFunction` to principal Service `s3.amazonaws.com`, scoped with a
  `Condition` `aws:SourceArn` equal to `arn:aws:s3:::ingest-source`. The AWS CLI
  shortcut is `aws lambda add-permission --principal s3.amazonaws.com --action
  lambda:InvokeFunction --source-arn arn:aws:s3:::ingest-source
  --statement-id s3invoke --function-name ingest`.
- Re-run the validator to confirm `policy_ok: true`, then re-upload a test object
  and confirm the Lambda is invoked in CloudWatch Logs.
- Leave the bucket notification rule unchanged — it was never the problem here,
  so no event-type or filter change is needed.
