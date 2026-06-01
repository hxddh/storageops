# STS Temporary Credentials

## STS Credential Structure

STS (Security Token Service) provides temporary credentials:
- `AccessKeyId` — Temporary access key.
- `SecretAccessKey` — Temporary secret key.
- `SessionToken` — MUST be included in requests (unlike long-term credentials).
- `Expiration` — UTC timestamp when credentials expire.

## STS Sources

### AssumeRole
```bash
aws sts assume-role --role-arn arn:aws:iam::123456789012:role/RoleName --role-session-name SessionName
```
Returns temporary credentials valid for the assumed role.

### GetSessionToken
```bash
aws sts get-session-token --duration-seconds 3600
```
Returns temporary credentials for the calling IAM user (with optional MFA).

### GetFederationToken
```bash
aws sts get-federation-token --name FederatedUser --policy <session-policy>
```
Returns temporary credentials for a federated user.

## Common STS Issues

### 1. Token Expiration
**Symptom:** Requests work initially, then fail with `ExpiredToken`.
**Cause:** Token passed its `Expiration` time.
**Check:** `aws sts get-caller-identity` — if it fails with expired token, refresh credentials.
**Action:** Re-assume the role or re-get session token.

### 2. Session Token Missing in Request
**Symptom:** `InvalidToken` or 403 with STS credentials.
**Cause:** The `x-amz-security-token` header (or `X-Amz-Security-Token`) is not included.
**Check:** Verify the tool or SDK is configured to send the session token.
- awscli: `aws_session_token` in `~/.aws/credentials` or `AWS_SESSION_TOKEN` env var.
- boto3: `aws_session_token` parameter or `AWS_SESSION_TOKEN` env var.
- s5cmd: `S5CMD_SESSION_TOKEN` or `AWS_SESSION_TOKEN` env var.

### 3. Role Trust Policy
**Symptom:** `AccessDenied` when calling `sts:AssumeRole`.
**Cause:** The role's trust policy does not trust the calling principal.
**Trust policy example:**
```json
{
  "Effect": "Allow",
  "Principal": {"AWS": "arn:aws:iam::123456789012:user/alice"},
  "Action": "sts:AssumeRole"
}
```
If Alice calls `sts:AssumeRole` for a role whose trust policy lists Bob, it will fail.

### 4. Session Policy Too Restrictive
**Symptom:** Assumed role works, but certain S3 operations fail.
**Cause:** The session policy passed during `AssumeRole` further restricts permissions.
Session policies can only RESTRICT, not expand, the role's permissions.

### 5. External ID
Some roles require an `ExternalId` condition for cross-account access:
```json
{
  "Effect": "Allow",
  "Principal": {"AWS": "arn:aws:iam::222222222222:root"},
  "Action": "sts:AssumeRole",
  "Condition": {"StringEquals": {"sts:ExternalId": "unique-id"}}
}
```
Missing ExternalId → AccessDenied on AssumeRole.

## S3-Compatible Provider STS

Not all S3-compatible providers have an STS service:
- **AWS:** Full STS support.
- **MinIO:** Supports STS (AssumeRoleWithWebIdentity, etc.).
- **BOS, OSS, COS, TOS:** Typically use long-term AK/SK or provider-specific STS (not AWS STS compatible).
- **Obsutil:** Uses OBS-specific authentication, not AWS STS.
- **bcecmd (BOS):** Uses Baidu-specific authentication.

If using awscli/rclone/s5cmd against a non-AWS S3-compatible provider with STS credentials,
the STS token may not be compatible with the provider's authentication model.

## Expiration Handling

STS token lifetime:
- `AssumeRole`: 15 min to 12 hours (configurable).
- `GetSessionToken`: 15 min to 36 hours.
- Longest practical: 12 hours.

Applications must handle token refresh:
- SDK automatic refresh (boto3 refreshes ~5 min before expiry).
- Manual refresh for CLI tools.
- Pre-signed URL expiry independent of STS token expiry.
