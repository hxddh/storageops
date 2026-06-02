# Summary

Category: event_notification
Route: storageops-event-notification
Confidence: 0.88
Root Cause Type: notification_filter_mismatch

SQS notification delivery fails because the configured prefix filter is
`images/`, while the object key is `uploads/images/cat.jpg`.

# Key Evidence

- Event type should be ObjectCreated.
- Destination is SQS.
- Key `uploads/images/cat.jpg` does not start with prefix `images/`.
- The `.jpg` suffix is compatible; the prefix is the mismatch.

# Remediation

Change the notification prefix to `uploads/images/` or adjust object placement so
keys match the existing prefix. Re-test notification delivery with a synthetic
ObjectCreated event.
