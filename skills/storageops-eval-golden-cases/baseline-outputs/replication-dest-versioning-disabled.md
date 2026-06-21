# Summary
Category: replication_versioning
Route: storageops-replication-versioning
Confidence: 0.88
Root Cause Type: dest_versioning_disabled
Evidence Quality: sufficient
Primary Diagnosis: root_cause_type=dest_versioning_disabled, affected_layer=dest-bucket

Replication is FAILED because the destination bucket has versioning disabled. S3
replication requires versioning enabled on both source and destination; the rule and
IAM role are fine.

# Key Evidence
- `get-bucket-versioning` on the destination (app-dr) returns empty — versioning is
  not enabled there, while the source has versioning enabled.
- Objects show replication status FAILED with the rule Enabled and the IAM role
  carrying the replication actions, isolating the cause to the destination bucket.

# Remediation
- Enable versioning on the destination bucket, then use S3 Batch Replication to
  backfill the objects written while replication was failing; new writes replicate
  automatically once destination versioning is on.
