# Routing
Category: event_notification
Route: storageops-event-notification
Confidence: 0.78
Root Cause Type: notification_filter_mismatch

A PUT Object that does not trigger the Lambda routes to event-notification: check the
notification rule prefix filter and the target permission.

# Evidence Gaps
- Need the bucket notification configuration (event type + prefix/suffix filter) and
  the target resource policy permission to confirm the mismatch.
