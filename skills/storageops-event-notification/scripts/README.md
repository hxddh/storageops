# Scripts

Deterministic, offline helpers for event-notification diagnosis. No network, no
LLM judgment — they parse the artifacts you already have and emit a verdict the
agent reasons over.

- `notification_config_analyzer.py` — Offline matcher for a bucket notification
  configuration. Given the notification JSON (e.g. `aws s3api
  get-bucket-notification-configuration` output), an object key, and an event,
  it reports whether a rule would fire (`would_fire`) or why it would not
  (`no_notification_config` / `event_type_mismatch` / `filter_mismatch`).
  Run when: events are not delivered and you have the notification configuration JSON.
  Example:
  `python3 scripts/notification_config_analyzer.py --config notif.json --key uploads/a.jpg --event s3:ObjectCreated:CompleteMultipartUpload --json`

- `notification_target_policy_validator.py` — Offline validator for a TARGET
  resource policy (Lambda get-policy / SQS or SNS `Policy` attribute). Checks
  deterministically whether the policy lets S3 deliver events: Principal Service
  `s3.amazonaws.com`, the right action (`lambda:InvokeFunction` / `sqs:SendMessage`
  / `sns:Publish`), and — when a bucket ARN is given — a matching `aws:SourceArn`
  condition. Emits `{"policy_ok": bool, "missing": [...], "suggested_statement": {...}}`.
  Target type is auto-detected from the policy or set with `--target-type`.
  Run when: the notification rule would fire but events still are not delivered
  (the #1 cause: target policy does not allow S3).
  Example:
  `python3 scripts/notification_target_policy_validator.py --file target-policy.json --target-type lambda --source-bucket-arn arn:aws:s3:::my-bucket`
