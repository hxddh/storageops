# Access Log Pattern Reference

Map of common access log patterns → likely root cause → routing to specialist skill.

## Status Codes

| Pattern | Root Cause | Route To |
|---------|-----------|----------|
| 429 SlowDown on single key, >10% of total requests | Hot key — S3 partition throttling | storageops-performance-diagnosis |
| 429 SlowDown across all keys | Account-level rate limit | storageops-performance-diagnosis |
| 503 SlowDown on single key | Hot key — server-side throttling | storageops-performance-diagnosis |
| 403 AccessDenied, requester is external IP | Public bucket or misconfigured policy | storageops-security-iam-policy |
| 403 AccessDenied, requester is VPC IP | IAM policy, VPC endpoint policy, or KMS key permission | storageops-security-iam-policy |
| 403 SignatureDoesNotMatch | Wrong region, clock skew, or wrong credentials | storageops-s3-protocol-compatibility |
| 400 InvalidArgument | Malformed request — tool/SDK bug or unsupported parameter | storageops-s3-protocol-compatibility |
| 500 InternalError | Provider-side issue, check provider status dashboard | Escalate to provider support |
| 404 NoSuchKey (GET) | Object deleted, wrong key, versioning issue | storageops-data-consistency |
| 404 NoSuchBucket | Bucket deleted or wrong region | storageops-s3-protocol-compatibility |
| 301 PermanentRedirect | Wrong region for bucket | storageops-s3-protocol-compatibility |

## Traffic Patterns

| Pattern | Root Cause | Route To |
|---------|-----------|----------|
| DELETE spike from new IP | Possible credential compromise | storageops-security-iam-policy (urgent) |
| High GET-to-LIST ratio (LIST > 50% of requests) | Inefficient client traversal | storageops-lifecycle-cost |
| Bandwidth/utilization flatline at a ceiling | Provider bandwidth cap or throttling | storageops-performance-diagnosis |
| Traffic drops to zero for extended period | Client crash, network outage, or provider outage | storageops-network-endpoint-access |
| Regular, weekly traffic spike | Expected workload pattern | Informational — no action needed |
| Traffic well above baseline but no errors | Organic growth — capacity planning | storageops-lifecycle-cost |

## Time Patterns

| Pattern | Root Cause | Route To |
|---------|-----------|----------|
| Errors cluster in 5-10 minute windows | Partition rebalancing or maintenance event | storageops-performance-diagnosis |
| Errors only during specific hours | Time-correlated workload (e.g., batch job) | Informational — schedule optimization |
| Latency spikes without error increase | Network congestion or provider-side slowdown | storageops-network-endpoint-access |
| Gradual latency increase over days | Resource exhaustion, metadata amplification | storageops-performance-diagnosis |

## Request Source Patterns

| Pattern | Root Cause | Route To |
|---------|-----------|----------|
| External IP with >100K requests, 98%+ 403 | Bucket enumeration attack | storageops-security-iam-policy (urgent) |
| Same IP using 3+ different user agents | Credential sharing or compromised key | storageops-security-iam-policy |
| Requests from unexpected regions | Potential credential leak or misconfigured CDN | storageops-security-iam-policy |
