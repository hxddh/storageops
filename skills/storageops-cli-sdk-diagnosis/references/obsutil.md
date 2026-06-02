# obsutil (Huawei Cloud OBS Utility) Analysis

obsutil is the official CLI tool for Huawei Cloud Object Storage Service (OBS).

## Scope

This reference applies to Huawei `obsutil` CLI usage. Do not apply its
configuration file, flags, or signing behavior to AWS CLI, rclone, SDKs, or
other provider-native tools.

## Verify Before Applying

Confirm the user is actually running `obsutil` and identify the active config:

```bash
./obsutil version
./obsutil config -help
```

## Version Check
```bash
./obsutil version
```

## Key Configuration

Configured via `./obsutil config -i=<AK> -k=<SK> -e=<endpoint>`.

Configuration stored in `~/.obsutilconfig` (plaintext credentials — REDACT).

## Key Parameters

| Parameter | Default | Notes |
|---|---|---|
| `-e` / `--endpoint` | (required) | OBS endpoint |
| `-i` / `--ak` | (required) | Access key |
| `-k` / `--sk` | (required) | Secret key |
| `-t` / `--token` | (empty) | Session token |
| `-p` / `--ps` | auto | Part size for multipart |
| `-c` / `--cpd` | auto | Concurrent parts |
| `-j` / `--jobs` | auto | Concurrent tasks |
| `-u` / `--update` | false | Update mode |
| `-v` / `--version` | false | Version ID |
| `-acl` | (empty) | Object ACL |
| `-sc` / `--storageClass` | STANDARD | Storage class |
| `-d` / `--dryRun` | false | Dry run |

## Debug Output
```bash
./obsutil ls obs://bucket -d
```

The `-d` flag enables debug output. Key sections:
- Request URL with query parameters
- Signature components
- Request/response headers

## Common obsutil Issues

### 1. SignatureDoesNotMatch Against S3-Compatible Endpoints

**This is the most common obsutil issue.**

obsutil uses OBS's signing algorithm which differs from AWS SigV4:
- The canonical request format may differ.
- The StringToSign format may differ.
- Headers included in signing may differ.

**When using obsutil against non-OBS endpoints:**
- obsutil is designed for Huawei OBS, not generic S3-compatible storage.
- Signature mismatches are expected and typically not fixable via configuration.
- Use awscli, s5cmd, or rclone for non-OBS endpoints.

**When using obsutil against OBS:**
- Verify endpoint is correct (region-specific: `obs.cn-north-4.myhuaweicloud.com`).
- Verify credentials are correct.
- Check clock sync.

### 2. Multipart Configuration
- obsutil auto-selects part size and concurrency based on file size.
- Manual override: `-p` for part size, `-c` for concurrent parts.
- Large file uploads benefit from tuning these.
- AWS S3 multipart parts are incompatible with OBS multipart (different initiation).

### 3. Parallel Jobs
- `-j` controls concurrent tasks (separate objects).
- `-c` controls concurrent parts within a single multipart upload.
- High `-j` × high `-c` = very high concurrency → possible throttling.

### 4. Path Style
- OBS uses path-style by default: `https://<endpoint>/<bucket>/<key>`.
- Virtual-hosted style may require DNS configuration and bucket naming rules.

### 5. Bucket Naming
- OBS has specific bucket naming rules that may differ from AWS S3.
- Bucket names may need to match region and account constraints.

## Secrets in Config

`~/.obsutilconfig` contains AK/SK in plaintext. Never read this file into
conversation context without redacting all credential lines.
