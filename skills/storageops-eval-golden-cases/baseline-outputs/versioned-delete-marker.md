# Summary
Category: replication_versioning
Route: storageops-replication-versioning
Confidence: 0.88
Root Cause Type: delete_marker_masking_versions
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=delete_marker_masking_versions, affected_layer=source-bucket

Objects "disappeared" because a DeleteObject without a VersionId created delete
markers that mask the still-present noncurrent versions; the data is recoverable.

# Key Evidence
- A delete marker is now IsLatest while prior versions remain; the DeleteObject call
  omitted a VersionId, so it added a marker rather than removing data.

# Recommendations
- Run list-object-versions to enumerate the delete marker and the masked VersionId,
  then remove the delete marker (or copy the desired VersionId forward) to restore.
