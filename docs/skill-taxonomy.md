# Skill Taxonomy

The taxonomy gives golden cases a stable vocabulary that does not depend on prose wording or skill filenames changing over time.

The source of truth is:

```text
docs/skill-taxonomy.json
```

## Rules

- Every golden-case `expected_category` must be canonical.
- Every category maps to one primary skill.
- Aliases are documentation aids; new cases should use canonical names.
- Routing cases should set `"case_type": "routing"`.
- Diagnosis cases should set `"case_type": "diagnosis"` or omit it.

## Categories

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

## Size Rules

- taxonomy JSON must stay under 20 KB,
- routing inputs should usually stay under 2 KB,
- golden-case input artifacts must stay under 10 KB,
- one golden case must stay under 25 KB.

These limits are enforced by `scripts/skill_integrity_check.py`.
