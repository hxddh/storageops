# Summary

Category: event_notification
Route: storageops-event-notification
Confidence: 0.9
Root cause type: event_type_mismatch (notification_filter_mismatch)

The bucket notification subscribes only to `s3:ObjectCreated:Put`. Single-PUT
uploads of small images fire it, but large images use the multipart API, which
emits `s3:ObjectCreated:CompleteMultipartUpload` — an event the rule does not
listen for — so the thumbnailer Lambda is never invoked. This is a
configuration/event-type problem, not a permission or corruption issue.

# Key Evidence

- Notification rule events: `s3:ObjectCreated:Put` only.
- Small files (<5MB) upload via a single PUT and trigger fine.
- Large files use `CreateMultipartUpload -> UploadPart -> CompleteMultipartUpload`
  and never trigger the Lambda.
- `scripts/notification_config_analyzer.py --config notification.json --event
  s3:ObjectCreated:CompleteMultipartUpload` returns verdict `event_type_mismatch`,
  confirming the rule cannot match a multipart completion.

# Remediation

- Add `s3:ObjectCreated:CompleteMultipartUpload` to the notification rule's
  events (or replace both with `s3:ObjectCreated:*` to cover every create path).
- Re-test with a large multipart upload and confirm the Lambda is invoked.
- The Lambda's resource policy is unchanged and was never the problem here, so no
  IAM change is needed for this fix.
