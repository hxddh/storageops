# Case: crr-replication-lag

## Summary

CRR (Cross-Region Replication) was configured from us-east-1 to eu-west-1.
All objects show `ReplicationStatus: FAILED` and CloudWatch shows 847 failed
replication operations in 24 hours.

## Root Causes

Two issues:

1. **Primary**: Destination bucket versioning is disabled (`get-bucket-versioning`
   returns `{}`). S3 replication requires versioning to be **Enabled** on both
   source and destination. Without it, S3 cannot write replicated objects to the
   destination, causing all replications to fail immediately.

2. **Secondary**: The IAM role is missing `s3:ReplicateDelete` permission.
   Even after versioning is fixed, delete marker propagation will fail.

3. **Informational**: Pre-existing objects (created before replication was configured)
   are not automatically replicated — this is expected behavior. S3 Batch Replication
   is required for historical objects.

## Expected Diagnosis

- Category: s3_protocol_compatibility, subcategory: replication
- Primary root cause: destination bucket versioning is not enabled
- Remediation: Enable versioning on prod-data-backup-eu-west-1 (manual-only)
- Secondary: add s3:ReplicateDelete to the IAM role if delete propagation is needed
- Note pre-existing objects require Batch Replication

## Key Evidence

- `get-bucket-versioning` on destination returns `{}` (not "Enabled")
- `ReplicationStatus: FAILED` on all recent objects
- `OperationsFailedReplication: 847` in CloudWatch
- `OperationsPendingReplication: 0` — objects were tried immediately and failed
