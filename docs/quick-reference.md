# Quick Reference

## Install

```bash
pip install storageops
storageops install
```

## Diagnose

```bash
storageops --print 's5cmd sync reports 429 SlowDown'
storageops --print @awscli-debug.log 'why is this SignatureDoesNotMatch?'
storageops
```

## Update

```bash
pip install --upgrade storageops
storageops install --force
```

## Skill Routing

| Symptom | Primary skill |
| --- | --- |
| Vague object-storage issue | `storageops-triage` |
| 403, AccessDenied, KMS deny | `storageops-security-iam-policy` |
| 429, SlowDown, throughput | `storageops-performance-diagnosis` |
| SignatureDoesNotMatch, CORS, malformed XML | `storageops-s3-protocol-compatibility` |
| rclone, s5cmd, awscli, boto3 | `storageops-cli-sdk-diagnosis` |
| DNS, TCP, TLS, VPC endpoint | `storageops-network-endpoint-access` |
| lifecycle or storage cost | `storageops-lifecycle-cost` |
| replication, versioning, delete markers | `storageops-replication-versioning` |
| s3fs/FUSE/workspace mounts | `storageops-mount-filesystem-workspace` |
| migration or sync plans | `storageops-migration-sync` |
| stale reads, ETag, checksum semantics | `storageops-data-consistency` |
| Spark, Hive, Trino, S3A | `storageops-bigdata-pipeline` |
| SQS/SNS/Lambda notifications | `storageops-event-notification` |
| server access logs and requester attribution | `storageops-access-log-analysis` |

## Useful Helper Scripts

```bash
python3 skills/storageops-s3-protocol-compatibility/scripts/parse_sigv4_error.py error.xml --json
python3 skills/storageops-network-endpoint-access/scripts/endpoint_reachability_test.py https://s3.example.com
python3 skills/storageops-eval-golden-cases/scripts/eval_all.py --cases skills/storageops-eval-golden-cases/cases --outputs diagnoses --json-out eval-current.json
```

## Validate

```bash
python3 scripts/skill_integrity_check.py
make validate
.venv/bin/python -m pytest
```
