# Tutorial

These examples show how to use StorageOps without exposing credentials or granting cloud account access.

## 1. 429 SlowDown

```bash
storageops --print 's5cmd sync s3://bucket/data ./data fails with 429 SlowDown'
```

Good evidence to include:

- tool and version,
- command shape,
- concurrency settings,
- object count and average size,
- whether errors cluster by prefix.

StorageOps should route to `storageops-performance-diagnosis`.

## 2. SignatureDoesNotMatch

```bash
storageops --print @error-response.xml 'why does this S3-compatible endpoint reject the signature?'
```

For saved XML/debug traces, use the helper:

```bash
python3 skills/storageops-s3-protocol-compatibility/scripts/parse_sigv4_error.py \
  error-response.xml --json
```

StorageOps should inspect credential scope, region, signed headers, payload hash, and canonical request shape.

## 3. Endpoint Timeout

```bash
storageops --print 'EC2 in private subnet times out connecting to s3.us-east-1.amazonaws.com'
```

If the user explicitly wants an active check from this machine:

```bash
python3 skills/storageops-network-endpoint-access/scripts/endpoint_reachability_test.py \
  https://s3.us-east-1.amazonaws.com --skip-http
```

StorageOps should distinguish DNS, TCP, TLS, and application-layer failures.

## 4. Access Log Investigation

```bash
storageops --print @access-log-sample.txt 'identify who caused this 503 spike'
```

StorageOps should route to access-log analysis, aggregate by requester and operation, then escalate to performance only after attribution.

## 5. Generate a Report

```bash
storageops --print @diagnosis-notes.md 'turn this into a customer-facing report'
```

StorageOps should route to `storageops-evidence-reporting` and preserve:

- summary,
- key evidence,
- root cause,
- recommendations,
- limitations and confidence.
