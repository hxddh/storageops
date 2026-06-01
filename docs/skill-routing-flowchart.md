# Skill Routing Flowchart

```text
user evidence
  |
  v
storageops-triage
  |
  +-- security_iam_policy --------> storageops-security-iam-policy
  +-- s3_protocol_compatibility --> storageops-s3-protocol-compatibility
  +-- performance_throughput -----> storageops-performance-diagnosis
  +-- network_endpoint_access ----> storageops-network-endpoint-access
  +-- cli_sdk_behavior -----------> storageops-cli-sdk-diagnosis
  +-- lifecycle_cost -------------> storageops-lifecycle-cost
  +-- replication_versioning -----> storageops-replication-versioning
  +-- mount_filesystem_workspace -> storageops-mount-filesystem-workspace
  +-- migration_sync -------------> storageops-migration-sync
  +-- consistency_integrity ------> storageops-data-consistency
  +-- bigdata_pipeline -----------> storageops-bigdata-pipeline
  +-- event_notification ---------> storageops-event-notification
  +-- access_log_analysis --------> storageops-access-log-analysis
```

## First Route

| Evidence | Primary route |
| --- | --- |
| exact 403 AccessDenied, policy, KMS | security |
| SignatureDoesNotMatch, malformed XML, CORS | protocol |
| 429, SlowDown, throughput, hot prefix | performance |
| DNS, TCP, TLS, VPC endpoint | network |
| rclone, s5cmd, awscli, boto3, SDK stack trace | CLI/SDK |
| lifecycle rules, IA/Glacier, cost | lifecycle-cost |
| CRR/SRR, delete marker, object lock | replication-versioning |
| s3fs, FUSE, mounted workspace | mount-filesystem |
| cross-provider copy, verification, metadata parity | migration-sync |
| stale read, ETag, checksum semantics | data-consistency |
| Spark, Hive, Trino, S3A committer | bigdata |
| SQS/SNS/Lambda event delivery | event-notification |
| server access logs, requester attribution | access-log-analysis |

## Common Cross-Routes

| Start | Escalate when |
| --- | --- |
| security -> protocol | 403 contains SignatureDoesNotMatch. |
| CLI/SDK -> protocol | debug log exposes ETag, SigV4, multipart, or CORS mismatch. |
| performance -> network | slow request has high RTT, DNS, TLS, or timeout evidence. |
| mount -> performance | root cause is metadata amplification. |
| replication -> security | cross-account role or KMS permission appears. |
| access-log -> security | 403 spike maps to one principal or policy change. |
| access-log -> performance | logs show 503/SlowDown or hot prefix. |

## Reporting

After specialist diagnosis, route to `storageops-evidence-reporting` when the user asks for customer-facing, internal, or reproducibility documentation.
