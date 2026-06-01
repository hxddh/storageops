# Skill Dependency Map

StorageOps skills are independent entry points, but many diagnoses need cross-skill checks.

## Core Dependencies

| Skill | Depends on | Used by |
| --- | --- | --- |
| `storageops-triage` | taxonomy, signatures, evidence rules | all specialist routes |
| `storageops-evidence-reporting` | reporting templates | all final reports |
| `storageops-eval-golden-cases` | taxonomy, cases, eval scripts | release and regression checks |

## Specialist Dependencies

| Skill | Common supporting skills |
| --- | --- |
| `storageops-security-iam-policy` | protocol, replication, access logs |
| `storageops-s3-protocol-compatibility` | CLI/SDK, network |
| `storageops-cli-sdk-diagnosis` | protocol, performance, network |
| `storageops-performance-diagnosis` | network, mount, access logs |
| `storageops-network-endpoint-access` | protocol for TLS/provider quirks |
| `storageops-lifecycle-cost` | access logs, performance |
| `storageops-replication-versioning` | security, network |
| `storageops-mount-filesystem-workspace` | performance, data consistency |
| `storageops-migration-sync` | data consistency, protocol, lifecycle |
| `storageops-data-consistency` | CLI/SDK, migration, mount |
| `storageops-bigdata-pipeline` | performance, protocol |
| `storageops-event-notification` | security, access logs |
| `storageops-access-log-analysis` | security, performance, lifecycle |

## Deterministic Helpers

| Domain | Helper |
| --- | --- |
| protocol | `parse_sigv4_error.py` |
| network | `endpoint_reachability_test.py` |
| access logs | `parse_access_log.py` |
| CLI/SDK | `parse_s5cmd_log.py` |
| security | `policy_analyzer.py` |
| performance | `throttle_detector.py` |
| data consistency | `etag_parser.py` |
| lifecycle | `small_object_analyzer.py` |
| migration | `migration_cost_estimator.py` |
| eval | `golden_case_validator.py`, `eval_runner.py`, `eval_all.py`, `unsafe_output_scanner.py`, `regression_reporter.py` |

## Maintenance Rule

When a skill starts relying on another skill's concept, add one of:

- a cross-route example,
- a golden case,
- a helper-script output field,
- or a reference note.
