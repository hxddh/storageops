# Required Evidence by Domain

For each diagnostic domain, the minimum evidence needed before a confident diagnosis
can be rendered.

## signature_auth

- [ ] Full error message with SignatureDoesNotMatch details
- [ ] Canonical request (if available in debug log)
- [ ] StringToSign (if available in debug log)
- [ ] Client endpoint/region configuration
- [ ] SDK/tool name and version
- [ ] Whether virtual-hosted-style or path-style is used
- [ ] Timestamp of the request (to check clock skew)

## permission_access_denied

- [ ] Full 403 error response body (XML/JSON)
- [ ] Bucket name and object key (if applicable)
- [ ] Action being attempted (s3:GetObject, s3:PutObject, etc.)
- [ ] IAM user/role ARN (if known)
- [ ] Bucket policy (if accessible, redacted)
- [ ] Whether STS or temporary credentials are in use

## s3_protocol_compatibility

- [ ] Provider name and advertised S3 compatibility version
- [ ] Failing request HTTP method and path
- [ ] Request headers sent
- [ ] Response status code and headers
- [ ] Response body
- [ ] Expected behavior per AWS S3 documentation
- [ ] Observed behavior difference

## cli_sdk_behavior

- [ ] Tool name and exact version
- [ ] Configuration file (redacted)
- [ ] Command line (redacted credentials)
- [ ] Debug/trace output
- [ ] Expected behavior
- [ ] Observed behavior
- [ ] Whether the same operation works with another tool

## performance_throughput

- [ ] Command and tool used
- [ ] Object sizes and count
- [ ] Concurrency and part size settings
- [ ] Observed throughput (MB/s)
- [ ] Expected or baseline throughput
- [ ] Client machine specs (CPU, memory, disk type)
- [ ] Network: RTT to endpoint, bandwidth capacity
- [ ] Any 429/503/5xx errors in logs
- [ ] Timing breakdown (connect, TLS, TTFB, transfer)

## mount_filesystem_workspace

- [ ] Mount type (s3fs, rclone mount, ossfs, bosfs, gcsfuse, Mountpoint for S3)
- [ ] Mount options (flags, cache settings, stat cache TTL)
- [ ] Workspace layout description (git repos, node_modules, venv, etc.)
- [ ] Timing comparison (local SSD vs mount)
- [ ] Kernel log / FUSE errors (`dmesg | grep -i fuse`)
- [ ] Stat/open/list call counts if available
- [ ] Filesystem type (ext4, xfs, APFS, etc.)

## network_endpoint_access

- [ ] Endpoint URL or hostname
- [ ] DNS resolution output (`dig`, `nslookup`)
- [ ] Access path type (public, VPC, PrivateLink, direct connect)
- [ ] TLS version and certificate chain (if applicable)
- [ ] MTU path discovery results
- [ ] RTT measurement (`ping`, `mtr`)
- [ ] Tracepath/traceroute to endpoint
- [ ] HTTP proxy or NAT configuration

## security_iam_policy

- [ ] Error message with request ID
- [ ] IAM policy JSON (redacted where needed)
- [ ] Bucket policy JSON (redacted where needed)
- [ ] Identity type (IAM user, role, STS, account root)
- [ ] Action and resource ARN being attempted
- [ ] Condition keys in use (if any)

## lifecycle_cost

- [ ] Lifecycle configuration (XML or equivalent)
- [ ] Storage class of objects in question
- [ ] Object sizes and count per prefix
- [ ] Transition/expiration rules
- [ ] Minimum storage duration of current storage class
- [ ] Access frequency patterns (hot/warm/cold)
- [ ] Region and pricing tier
