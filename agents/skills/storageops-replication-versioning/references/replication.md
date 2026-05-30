# Cross-Region and Same-Region Replication

## Overview

S3 replication copies objects asynchronously from a source bucket to one or more
destination buckets. Two modes:
- **CRR (Cross-Region Replication)** — source and destination in different AWS regions
- **SRR (Same-Region Replication)** — source and destination in the same region

Replication requires versioning to be **Enabled** (not Suspended) on both buckets.

---

## Prerequisites Checklist

| Requirement | Check | Failure Mode |
|---|---|---|
| Source bucket versioning: Enabled | `get-bucket-versioning` → `Status: Enabled` | Objects not queued for replication |
| Destination bucket versioning: Enabled | `get-bucket-versioning` on dest | Replication role gets `InvalidRequest` |
| Replication IAM role exists | `get-bucket-replication` → `Role` ARN | `InvalidArgument` on replication config |
| IAM role trust: s3.amazonaws.com | Role trust policy | `AccessDenied` when S3 assumes role |
| IAM role permission: source read | `s3:GetObjectVersionForReplication` | Objects stuck PENDING |
| IAM role permission: dest write | `s3:ReplicateObject` on dest | Objects FAILED |
| Cross-account dest bucket policy | Allows source account replication role | `Forbidden` FAILED status |
| KMS: cross-account key access | Dest account can use source KMS key | KMS-related FAILED |

---

## IAM Role Minimum Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetReplicationConfiguration",
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::<source-bucket>"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObjectVersionForReplication",
        "s3:GetObjectVersionAcl",
        "s3:GetObjectVersionTagging"
      ],
      "Resource": "arn:aws:s3:::<source-bucket>/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ReplicateObject",
        "s3:ReplicateDelete",
        "s3:ReplicateTags"
      ],
      "Resource": "arn:aws:s3:::<destination-bucket>/*"
    }
  ]
}
```

---

## Destination Bucket Policy (Cross-Account)

When the destination bucket is in a different AWS account, the destination bucket
policy must explicitly allow the source account's replication role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReplicationFromSourceAccount",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<source-account-id>:role/<replication-role-name>"
      },
      "Action": [
        "s3:ReplicateObject",
        "s3:ReplicateDelete",
        "s3:ReplicateTags",
        "s3:GetObjectVersionTagging"
      ],
      "Resource": "arn:aws:s3:::<destination-bucket>/*"
    }
  ]
}
```

---

## ReplicationStatus Values

Check per-object via `head-object`:

| Status | Meaning |
|---|---|
| `PENDING` | Queued, replication not yet started |
| `COMPLETED` | Successfully replicated to destination |
| `FAILED` | Replication attempt failed (check CloudWatch for reason) |
| `REPLICA` | This object IS the destination replica |

Objects created before replication was enabled are NOT automatically replicated.
Use S3 Batch Replication to replicate existing objects.

---

## Delete Marker Propagation

Delete marker replication is **opt-in**. For replication rules created before
November 2020, delete markers are NOT propagated by default.

To check: `get-bucket-replication` → look for `DeleteMarkerReplication.Status`.
- `Enabled` → delete markers propagate
- `Disabled` or absent → delete markers do NOT propagate

**Impact:** If delete marker replication is disabled:
- Deleting an object in the source creates a delete marker in the source
- The destination still has the object with no delete marker
- `GetObject` on source returns 404; on destination returns the object

To enable (manual-only): update the replication rule to set `DeleteMarkerReplication.Status: Enabled`.

---

## KMS-Encrypted Object Replication

If source objects are encrypted with SSE-KMS:
1. The replication role must have `kms:Decrypt` on the source KMS key
2. The replication rule must specify a destination KMS key ARN
3. The replication role must have `kms:GenerateDataKey` on the destination KMS key
4. For cross-account: the destination KMS key policy must allow the source account's replication role

---

## CloudWatch Replication Metrics

Enable S3 Replication Time Control (RTC) or Replication Metrics to get visibility:

| Metric | Description |
|---|---|
| `OperationsPendingReplication` | Objects queued but not yet replicated |
| `OperationsFailedReplication` | Failed replication operations |
| `ReplicationLatency` | Time in seconds for replication (with RTC) |
| `BytesPendingReplication` | Total bytes awaiting replication |

---

## S3 Batch Replication

Existing objects created before replication was enabled are not automatically replicated.
To replicate them, use S3 Batch Replication:
1. Create a Batch Operations job using the `S3PutObjectCopy` operation
2. Use an S3 Inventory to identify objects to replicate
3. This generates API calls at scale and has associated costs

---

## Common Failure Root Causes

| Symptom | Most Likely Root Cause |
|---|---|
| All objects FAILED | Destination bucket policy missing |
| Objects PENDING indefinitely | Replication role lacks source read permission |
| Specific objects FAILED | KMS cross-account permission or storage class mismatch |
| Deletes not propagating | Delete marker replication not enabled |
| Pre-existing objects missing | Objects created before replication was configured; use Batch Replication |
| New objects not replicating | Replication configuration added after objects were created AND no filter matches |
