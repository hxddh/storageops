# Summary

Category: migration_sync
Route: storageops-migration-sync
Confidence: 0.88
Root cause type: metadata_not_preserved (content_type_mismatch)

The migration copied object bytes but did not preserve user metadata: the
destination `public/app.js` has `Content-Type: application/octet-stream` and a
missing `Cache-Control`, while the source had `Content-Type: application/javascript`
and `Cache-Control: public,max-age=...`. Browsers then download the file instead
of executing it. The ETag matches, so the data itself is intact — this is a
metadata-preservation problem, not corruption.

# Key Evidence

- Source HEAD: `Content-Type: application/javascript`, `Cache-Control:
  public,max-age=31536000,immutable`.
- Destination HEAD: `Content-Type: application/octet-stream`, `Cache-Control`
  missing.
- ETag identical on both sides (`"abc123"`) — bytes transferred correctly.
- Symptom (browser downloads JS) follows directly from the wrong Content-Type.

# Remediation

- Re-copy preserving metadata: use the tool's metadata flags (e.g. rclone
  `--metadata`, or set `--header-upload "Content-Type: application/javascript"`)
  so `Content-Type` and `Cache-Control` survive the transfer.
- Verify each fixed object with a destination `HEAD` and compare headers to the
  source before and after.
- If a transfer log is available, `python3 scripts/sync_log_analyzer.py --log
  <log>` flags a `metadata` error class, confirming metadata was not preserved
  across the run rather than lost only on this object.
- Do not re-run a destructive sync to "fix" this — it would not restore metadata
  and risks deleting good objects.
