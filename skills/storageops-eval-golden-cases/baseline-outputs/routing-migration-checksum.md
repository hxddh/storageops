# Routing
Category: migration_sync
Route: storageops-migration-sync
Confidence: 0.78
Root Cause Type: cross_provider_checksum

A checksum mismatch reported by rclone after objects were migrated routes to
migration-sync: verify integrity with an explicit checksum rather than the multipart
ETag, instead of a blind re-copy.

# Evidence Gaps
- Need the source/destination providers and a sample object's size and ETag to confirm
  the mismatch is a cross-provider multipart-ETag format difference, not corruption.
