# Scripts

- `replication_status_analyzer.py` — Offline, deterministic classifier for S3
  replication/versioning evidence. Reads `get-bucket-replication` /
  `get-bucket-versioning` / `head-object` output and/or free-text logs via
  `--file` or `--stdin`, then emits a JSON object
  `{ok, summary, root_cause, findings, recommendation}`. Never contacts a bucket.

  Detected root causes (priority order): `dest_versioning_disabled`,
  `source_versioning_suspended`, `rule_disabled`,
  `delete_marker_not_replicated`, `replication_failed`, `healthy`.

  Usage:
  ```
  python3 replication_status_analyzer.py --file evidence.txt
  cat evidence.txt | python3 replication_status_analyzer.py --stdin
  ```

  Robust to empty/malformed input (emits `ok: false` JSON, never a traceback).
