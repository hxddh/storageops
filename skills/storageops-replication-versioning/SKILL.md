---
name: storageops-replication-versioning
description: >
  Diagnose object storage replication delays, missing replicas, versioning
  inconsistencies, delete marker propagation, and object lock compliance
  issues. Covers cross-region replication (CRR), same-region replication (SRR),
  and provider-specific replication features. Use when user reports replication
  lag, version mismatch, or object lock not working as expected.
maturity: stable
mode: light_heavy
estimated_tokens: 1300
trigger_keywords:
  - replication
  - CRR
  - SRR
  - cross-region replication
  - versioning
  - delete marker
  - object lock
  - legal hold
  - retention
  - replica lag
  - replication failure
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# Replication & Versioning Diagnosis

Replication issues fall into three categories: configuration (rules not matching), operation (replication failing), and versioning (unexpected object state).

## Decision Tree

```
Replication/versioning issue →
  ├─ "Objects not replicating"? →
  │   ├─ Replication rule exists? → Check rule filter (prefix/tag/status)
  │   ├─ Versioning enabled on BOTH source AND destination? → Required
  │   ├─ IAM role has s3:ReplicateObject + s3:ObjectOwnerOverrideToBucketOwner?
  │   └─ Object created before replication rule? → Not retroactive (use S3 Batch)
  ├─ "Delete markers not replicating"? →
  │   └─ Check: DeleteMarkerReplication enabled in rule?
  ├─ "Replication lag (hours behind)"? →
  │   ├─ Large backlog? → Check replication metrics (CloudWatch/S3 metrics)
  │   ├─ Cross-region latency? → Normal: 15 min SLA for 99.9% of objects
  │   └─ Large objects + slow link? → Replication time ≈ object size / bandwidth
  ├─ "Object lock not working"? →
  │   ├─ Object lock enabled at bucket creation? → Must be at create time
  │   ├─ Retention mode: GOVERNANCE vs COMPLIANCE? → COMPLIANCE can't be overridden
  │   └─ Legal hold applied? → Prevents deletion regardless of retention
  └─ "Version ID mismatch"? → Check versioning state: Enabled vs Suspended
```

## Workflow

### Step 1: Verify Configuration
Three pre-requisites for replication: versioning enabled on BOTH buckets, replication rule on source bucket, IAM role with correct permissions (`s3:ReplicateObject`, `s3:ReplicateDelete`, `s3:ReplicateTags`).

### Step 2: Replication Diagnosis
- **Missing replicas**: Check replication rule filter (prefix/tags), object creation time vs rule creation time, delete marker replication setting
- **Replication lag**: Check S3 Replication Time Control (RTC, SLA 15 min). Cross-region latency is normal.
- **Failed replication**: Check source object ownership (bucket owner must own object), KMS-encrypted objects need additional KMS grant to replication role

### Step 3: Delete Marker Propagation
Delete markers replicate ONLY if `DeleteMarkerReplication` is enabled in the rule. Without it, deleting a source object leaves the replica intact.

### Step 4: Versioning State Machine
- **Unversioned** → **Versioning-enabled** (irreversible): existing objects get versionId=null
- **Versioning-enabled** → **Suspended**: new objects get versionId=null, existing versions preserved
- **Suspended** → **Versioning-enabled**: resumes versioning for new objects

### Step 5: Object Lock Diagnosis
- Object Lock must be enabled at bucket creation (cannot be added later)
- Default retention applies to all new objects; explicit retention overrides default
- GOVERNANCE mode: `s3:BypassGovernanceRetention` permission can override
- COMPLIANCE mode: NO ONE can override (including root) until retention expires

## Output Format

```markdown
# Diagnosis: [one-line]
**Subsystem**: replication-rule | replication-lag | delete-marker | versioning | object-lock
**Confidence**: high | medium | low

## Evidence
- Source bucket: [versioning state, replication rules]
- Destination bucket: [versioning state, region]
- IAM role: [permissions summary]

## Root Cause
[Explanation with config evidence]

## Recommendations
1. **[config fix]** (manual-only) — [expected effect]
2. **[retroactive fix]** — [S3 Batch Replication for existing objects]
```

## Examples

### Example 1: Replication not working — missing versioning on destination
**Input**: Objects not replicating from us-east-1 to ap-southeast-1. Rule appears correct.
**Diagnosis**: Versioning enabled on source, SUSPENDED on destination. Replication requires versioning on both buckets.
**Recommendation**: Enable versioning on destination bucket (irreversible). Existing objects need S3 Batch Replication job.

### Example 2: Delete markers not replicating
**Input**: Deleted source object → replica still exists in destination.
**Diagnosis**: `DeleteMarkerReplication` not enabled in replication rule. Default is disabled.
**Recommendation**: Update rule: `DeleteMarkerReplication: {Status: Enabled}`. Existing delete markers need manual cleanup on destination.

### Example 3: Object lock COMPLIANCE mode — can't delete
**Input**: Object with retention until 2028, COMPLIANCE mode. Needs to delete for legal reasons.
**Diagnosis**: COMPLIANCE mode retention cannot be overridden by anyone, including root account.
**Recommendation**: Wait for retention expiry. If urgent, contact provider support (AWS can't override COMPLIANCE either). For future: use GOVERNANCE mode with s3:BypassGovernanceRetention permission.

## References
- `references/replication-configuration.md` — Replication rule schema and permissions
- `references/versioning-lifecycle.md` — Versioning state machine and cost implications
- `references/object-lock-guide.md` — Retention modes, legal hold, compliance
- `references/provider-replication.md` — Non-AWS replication (BOS/OSS/COS cross-region)
