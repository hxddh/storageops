# Summary

Category: replication_versioning
Route: storageops-replication-versioning
Confidence: 0.85
Root Cause Type: replication_destination_versioning_disabled

Cross-region replication shows `ReplicationStatus: FAILED` on every object because
versioning is not enabled on the destination bucket. S3 replication requires
versioning Enabled on both source and destination; with it off at the
destination, S3 cannot write replicas and every operation fails immediately.

# Key Evidence

- `get-bucket-versioning` on the destination `prod-data-backup-eu-west-1` returns
  `{}` — versioning is not enabled there (the source is confirmed Enabled).
- `head-object` reports `ReplicationStatus: FAILED`, and CloudWatch
  `OperationsFailedReplication` is 847 over 24h with `OperationsPendingReplication`
  at 0 — every object was tried and failed, matching a destination that rejects
  replicated writes.
- Secondary: the role lacks `s3:ReplicateDelete`, so delete-marker propagation
  will still fail after versioning is fixed; pre-existing objects need Batch
  Replication (expected behavior, not a failure).

# Recommendations

- Enable versioning on the destination bucket
  (`aws s3api put-bucket-versioning --bucket prod-data-backup-eu-west-1
  --versioning-configuration Status=Enabled`), then re-check with
  `get-bucket-versioning`; new objects should then replicate.
- Add `s3:ReplicateDelete` to the replication role so delete markers propagate.
- Use S3 Batch Replication to backfill objects created before replication was
  configured.
