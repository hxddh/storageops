# Quick Reference

## Install

```bash
python3 -m pip install storageops -i https://pypi.org/simple
storageops install
```

If a cloud or regional PyPI mirror cannot find the package:

```bash
python3 -m pip install --upgrade storageops -i https://pypi.org/simple
```

For Ubuntu/Debian `externally-managed-environment` errors on an isolated VM:

```bash
python3 -m pip install storageops --break-system-packages -i https://pypi.org/simple
```

## Model Key

```bash
export DEEPSEEK_API_KEY=sk-...
# or:
echo sk-... > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
# or:
storageops configure --provider deepseek --model deepseek-v4-pro --api-key
```

## Diagnose

```bash
storageops doctor
storageops smoke --provider deepseek --model deepseek-v4-pro
storageops --print 's5cmd sync reports 429 SlowDown'
storageops --print @awscli-debug.log 'why is this SignatureDoesNotMatch?'
storageops
```

## Update

```bash
python3 -m pip install --upgrade storageops -i https://pypi.org/simple
storageops install --force
```

`storageops install --force` redeploys files from the local package. It prints
the package version and path and writes `~/.storageops/install.json`.

For Ubuntu/Debian cloud hosts, or immediately after a new release when pip cache
or mirrors may lag:

```bash
python3 -m pip install --upgrade storageops --break-system-packages --no-cache-dir -i https://pypi.org/simple
storageops install --force
storageops --version
```

Trust the `StorageOps package: v...` line printed by `storageops install`; if it
is still old, pip did not upgrade the package and the old bundled skills were
redeployed.

## Skill Routing

| Symptom | Primary skill |
| --- | --- |
| Vague object-storage issue | `storageops-triage` |
| 403, AccessDenied, KMS deny | `storageops-security-iam-policy` |
| 429, SlowDown, throughput | `storageops-performance-diagnosis` |
| SignatureDoesNotMatch, BadDigest, CORS, malformed XML | `storageops-s3-protocol-compatibility` |
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

Run from the repository root. (`--outputs` points at a directory of saved model
diagnoses, one `<case-name>.md` per case; the repo's bundled examples live in
`skills/storageops-eval-golden-cases/baseline-outputs`.)

```bash
python3 skills/storageops-s3-protocol-compatibility/scripts/parse_sigv4_error.py error.xml --json
python3 skills/storageops-s3-protocol-compatibility/scripts/check_payload_hash.py \
  --raw-file out.json --declared-sha256 <hex> --content-encoding gzip --json
python3 skills/storageops-network-endpoint-access/scripts/endpoint_reachability_test.py https://s3.example.com
python3 skills/storageops-eval-golden-cases/scripts/eval_all.py \
  --cases skills/storageops-eval-golden-cases/cases \
  --outputs skills/storageops-eval-golden-cases/baseline-outputs --only-with-outputs
```

## Validate

```bash
python3 scripts/skill_integrity_check.py
python3 scripts/routing_contract_check.py
python3 scripts/repo_size_gate.py
python3 scripts/package_check.py
python3 skills/storageops-eval-golden-cases/scripts/eval_all.py --cases skills/storageops-eval-golden-cases/cases --outputs skills/storageops-eval-golden-cases/baseline-outputs --only-with-outputs
make validate
.venv/bin/python -m pytest
```
