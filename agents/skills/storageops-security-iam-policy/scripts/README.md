# storageops-security-iam-policy Scripts

Future scripts for this domain (not yet implemented in v0.1):

## Planned Scripts

### `secret_scanner.py`
Scan input files and flag potential secrets:
- AWS AK pattern: `AKIA[0-9A-Z]{16}`
- Authorization headers.
- Session tokens (base64, length > 500).
- Credential files (INI, JSON, YAML formats).
- Report locations with line numbers.
- Optionally redact and output sanitized version.

### `policy_analyzer.py`
Parse IAM and bucket policy JSON documents:
- Identify explicit Deny statements.
- Identify missing Allow statements.
- Check for `"Principal": "*"` (public access risk).
- Check for overly broad actions (`"s3:*"`, `"*"`).
- Flag condition keys that may restrict access unexpectedly.
- Report least-privilege violations.

### `access_denied_tracer.py`
Given a 403 error response, IAM policies, and bucket policy:
- Trace the policy evaluation logic.
- Determine which policy statement caused the denial.
- Identify what needs to change (manual-only recommendation).
- Report confidence level.

### `kms_permission_checker.py`
Given S3 operations and KMS key configuration:
- Check if the principal has `kms:Decrypt` and `kms:GenerateDataKey`.
- Estimate KMS API call rate for a given workload volume.
- Flag potential KMS rate limit issues for high-throughput workloads.

## Principles

- All scripts operate on offline policy documents and logs.
- Never connect to live AWS/cloud APIs to evaluate policies.
- Secret scanning must happen BEFORE any other processing.
- Redaction must be applied to script output as well.
