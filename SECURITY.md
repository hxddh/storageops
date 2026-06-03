# Security

StorageOps is built for diagnosis, not cloud account control. Its default posture is read-only, evidence-driven, and credential-averse.

## Runtime Surface

- `storageops_cli/__init__.py` installs and launches Pi.
- `storageops_cli/extensions/storageops.ts` registers four Pi tools
  (`scan_secrets`, `detect_domain`, `search_memory`, `capture_http_trace`). The
  first three run fully inline; `capture_http_trace` wraps the external `httpmon`
  binary through a bounded, read-only wrapper (no mutating commands, no body
  capture, no replay).
- `skills/` contains markdown instructions, references, scripts, templates, and eval cases.
- Domain helper scripts are local diagnostics. They must be offline or explicitly read-only.

StorageOps itself does not need access keys for object storage accounts. Model provider keys are only for the underlying Pi model runtime.

The optional `~/.storageops/agent/api-key` file stores a plaintext model-provider
key on disk; if you use it, restrict it with `chmod 600`. It accepts an optional
`provider:key` prefix to bind the key to a specific provider.

The optional `scripts/credential-loader.sh` helper is for user-run tools such as
DuckDB, rclone, and awscli. It loads credentials into the current shell so those
tools can read local environment variables; StorageOps should not print, store,
or send those credentials to a model.

## Secret Handling

The `scan_secrets` tool detects and redacts:

- AWS-style access keys, secret keys, and session tokens.
- Alibaba, Tencent, and Baidu credential shapes.
- Authorization headers and private key blocks (incl. GCP PKCS8 keys).
- rclone-style passwords and tokens.
- `sk-...` API keys and GitHub token shapes.
- Presigned-URL signature material (`X-Amz-Signature`/`X-Amz-Credential`/
  `X-Amz-Security-Token`, `X-Goog-Signature`, OSS `Signature`/`OSSAccessKeyId`,
  COS `q-signature`/`q-ak`).
- GCP service-account keys (`private_key`, `private_key_id`) and Azure storage
  account keys (`AccountKey=`) and SAS signatures (`sig=`).

Skill instructions and eval gates require diagnostic output to avoid leaking raw credentials.

## Safety Rules

StorageOps skills must not:

- request real AK/SK credentials for cloud accounts,
- execute destructive object storage operations,
- recommend making buckets public as a fix,
- recommend disabling TLS verification as a permanent fix,
- output raw credentials,
- treat user-provided logs as trusted instructions.

Potentially risky remediation must be framed as manual-only and should include validation or rollback guidance.

## Read-Only Active Checks

Some helper scripts can perform active checks against a user-supplied target, such as endpoint reachability. These checks must:

- operate only on endpoints the user is authorized to test,
- avoid credentials,
- avoid writes,
- report exactly which network layer was tested.

## Audit Trail

Pi manages sessions under the selected agent directory, such as:

```text
~/.storageops/agent/sessions/
~/.pi/agent/sessions/
```

Session contents may include user-provided logs. Users should redact sensitive data before sharing session files.

## Reporting Vulnerabilities

Report security issues privately to the repository maintainers. Do not open public issues containing secrets or exploitable details.
