# boto3 / botocore Exception Analysis

## Scope

This reference applies to Python applications using `boto3` and `botocore`.
Although botocore can read AWS shared config files, application code may also
pass credentials, endpoint, region, retries, and S3 addressing style directly.
Do not infer a CLI config path unless the evidence shows the SDK is using that
credential chain.

## Verify Before Applying

Confirm the SDK versions and how the client is constructed:

```python
import boto3, botocore
print(boto3.__version__)
print(botocore.__version__)
```

Ask for sanitized client construction code or debug logs before asserting which
credential source is active.

## Version Check
```python
import boto3, botocore
print(boto3.__version__)
print(botocore.__version__)
```

## Key Configuration

### Client Creation
```python
s3 = boto3.client('s3',
    endpoint_url='https://s3.example.com',
    region_name='us-east-1',  # Required for SigV4
    config=botocore.config.Config(
        retries={'max_attempts': 5, 'mode': 'standard'},
        connect_timeout=10,
        read_timeout=30,
        max_pool_connections=25,
        signature_version='s3v4',
        s3={'addressing_style': 'path'}  # or 'virtual'
    )
)
```

### Environment Variables
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
- `AWS_DEFAULT_REGION`, `AWS_REGION`
- `AWS_CA_BUNDLE`, `AWS_PROXY`

## Common Exceptions

### `ClientError`
Wrapper for service errors. Check:
- `error.response['Error']['Code']` — Error code
- `error.response['Error']['Message']` — Error message
- `error.response['ResponseMetadata']['HTTPStatusCode']` — HTTP status
- `error.response['ResponseMetadata']['RequestId']` — Request ID

### `EndpointConnectionError`
Cannot connect to endpoint. Check:
- Endpoint URL correct?
- DNS resolution?
- Network reachable?
- TLS certificate valid?

### `ConnectionClosedError` / `ReadTimeoutError`
Connection dropped or read timed out. Check:
- Timeout configuration.
- Server-side connection keepalive settings.
- Network stability.
- Large objects without proper timeout.

### `SignatureDoesNotMatch` (ClientError with code)
See `storageops-s3-protocol-compatibility/references/sigv4.md`.

### `NoCredentialsError`
No credentials found. Check credential chain order:
1. boto3 client params (`aws_access_key_id`, `aws_secret_access_key`)
2. Environment variables
3. `~/.aws/credentials`
4. IAM role (EC2, ECS, Lambda)
5. `~/.aws/config`

## Retry Configuration

botocore retry modes:
- `legacy` — Fixed retries (default 5).
- `standard` — Exponential backoff with jitter.
- `adaptive` — Standard + client-side rate limiting.

Retryable errors:
- 5xx server errors
- 429 (TooManyRequests) / SlowDown
- Connection errors
- NOT retryable: 4xx client errors (except 429)

## Connection Pool

`max_pool_connections` (default 10):
- Controls maximum concurrent connections to the endpoint.
- Too low → bottleneck for high-concurrency operations.
- Too high → may trigger server-side rate limiting.

## Address Style

`addressing_style`:
- `path` — `https://<endpoint>/<bucket>/<key>` (default for custom endpoints).
- `virtual` — `https://<bucket>.<endpoint>/<key>`.
- `auto` — Detect based on endpoint (default for AWS endpoints).

## Debug Logging

```python
import logging
boto3.set_stream_logger(name='botocore', level=logging.DEBUG)
```

This produces the same verbose output as awscli `--debug`. Secret redaction required.

## Common boto3/botocore Issues

### 1. Region Required for SigV4
- boto3 requires `region_name` even for custom endpoints.
- If not set, may try to read from `~/.aws/config` or environment.
- Missing region → `NoRegionError` or signature failure.

### 2. `s3v4` vs `s3` Signature Version
- `s3v4` uses SigV4 in Authorization header.
- Older `s3` uses SigV2 (deprecated by AWS, rarely supported by providers).

### 3. TransferConfig for Large Files
```python
from boto3.s3.transfer import TransferConfig
config = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,  # 8 MB
    max_concurrency=10,
    multipart_chunksize=8 * 1024 * 1024,  # 8 MB
    use_threads=True
)
s3.upload_file('file', 'bucket', 'key', Config=config)
```

### 4. Streaming Upload (UploadFileObj)
- Streaming uploads without Content-Length use chunked transfer encoding.
- Some S3-compatible providers do not support chunked encoding.
- Fix: Use `TransferConfig` with known file size, or read file into memory.
