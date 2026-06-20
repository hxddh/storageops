# Notification Configuration

## When to read
Use when S3 event notifications do not fire at all, fire for the wrong objects, or
the user provides the bucket notification configuration (XML/JSON). This is the
*source-side* check — whether the bucket is even configured to emit the event.
For the *target-side* check (does the destination accept delivery), see
`lambda-integration.md` / `sqs-integration.md` / `sns-integration.md`.

## Mental model
A notification rule fires only when **all** of these match the actual operation:
event type, key prefix, and key suffix (S3 evaluates them as an AND). A rule that
"looks right" but never fires is almost always a filter or event-type mismatch,
not a delivery failure. Delivery is silent: if the rule matches but the target
rejects, the caller sees no error — that is the target-side class.

## Checks (in order)
1. **Event type matches the operation.** `s3:ObjectCreated:Put` fires for a single
   PUT but **not** for a multipart completion — that is
   `s3:ObjectCreated:CompleteMultipartUpload`. Use `s3:ObjectCreated:*` if the
   writer may use either path. Copies are `s3:ObjectCreated:Copy`. Deletes are
   `s3:ObjectRemoved:*`; on a versioned bucket a delete-marker is
   `s3:ObjectRemoved:DeleteMarkerCreated`, not `Delete`.
2. **Prefix/suffix filters match the key exactly.** Filters are literal,
   case-sensitive substrings of the *decoded* key, with no globbing. `images/`
   matches `images/a.png` but not `Images/a.png`; suffix `.jpg` does not match
   `.jpeg` or `.JPG`. A leading `/` is **not** part of an S3 key, so a `/images/`
   prefix matches nothing.
3. **Destination ARN/region/account is correct.** The target must be reachable
   from the bucket's region and account; cross-region SNS/SQS targets are rejected
   at configuration time on most providers.
4. **No overlapping rules for the same event type.** AWS rejects two rules whose
   prefix/suffix overlap for the same event type at PutBucketNotification time. A
   "MalformedXML"/"configuration is ambiguous" error here means consolidate the
   rules — it is not a delivery problem.

## How to confirm
```bash
# What is actually configured on the bucket:
aws s3api get-bucket-notification-configuration --bucket <bucket>
# Decode the key you expect to match and compare against prefix/suffix literally.
```
Run `python3 scripts/notification_config_analyzer.py` on the saved configuration
to flag event-type/prefix/suffix mismatches deterministically.

## Caveats / verification status
- Event-type names above are AWS-verified. BOS/OSS/COS expose similar but **not
  identical** event taxonomies and filter semantics — confirm the exact event-type
  strings against the provider's docs before asserting a mismatch.
- EventBridge-mode notifications (when enabled) bypass the prefix/suffix filter and
  match in the EventBridge rule pattern instead; check the rule there.
