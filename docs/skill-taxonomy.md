# Skill Taxonomy

StorageOps golden cases use stable issue categories so routing, eval, and
documentation do not drift as skill names evolve.

## Contract

- The machine-readable taxonomy is `docs/skill-taxonomy.json`.
- Every `expected_category` in a golden case must exist in the taxonomy.
- Every taxonomy category maps to exactly one primary `storageops-*` skill.
- Category aliases are accepted for documentation and migration, but golden cases
  should use canonical category names.
- Routing cases should set `"case_type": "routing"` and keep input artifacts short.

## Canonical Categories

| Category | Primary skill |
| --- | --- |
| `access_log_analysis` | `storageops-access-log-analysis` |
| `bigdata_pipeline` | `storageops-bigdata-pipeline` |
| `cli_sdk_behavior` | `storageops-cli-sdk-diagnosis` |
| `consistency_integrity` | `storageops-data-consistency` |
| `cors_configuration` | `storageops-s3-protocol-compatibility` |
| `event_notification` | `storageops-event-notification` |
| `lifecycle_cost` | `storageops-lifecycle-cost` |
| `migration_sync` | `storageops-migration-sync` |
| `mount_filesystem_workspace` | `storageops-mount-filesystem-workspace` |
| `network_endpoint_access` | `storageops-network-endpoint-access` |
| `performance_throughput` | `storageops-performance-diagnosis` |
| `replication_versioning` | `storageops-replication-versioning` |
| `reporting` | `storageops-evidence-reporting` |
| `s3_protocol_compatibility` | `storageops-s3-protocol-compatibility` |
| `security_iam_policy` | `storageops-security-iam-policy` |
| `triage` | `storageops-triage` |

## Size Budget

Keep taxonomy and routing cases small:

- taxonomy stays under 20 KB unless a new diagnostic domain is added.
- routing case input should usually be under 2 KB.
- large real logs belong outside the main repo; commit only reduced, synthetic,
  redacted samples.
