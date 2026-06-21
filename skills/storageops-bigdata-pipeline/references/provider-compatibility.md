# Big Data Provider Compatibility

## When to read
Use when Spark / Hive / Flink / Hadoop (via the S3A connector) runs against a
non-AWS S3-compatible endpoint (Baidu BOS, Alibaba OSS, Tencent COS, Huawei OBS,
MinIO) and jobs fail at connect/sign/list/commit. S3A defaults are tuned for AWS;
non-AWS endpoints usually need explicit endpoint, path-style, and signing config.

> **Verify against your Hadoop/connector version.** The `fs.s3a.*` keys below are
> stable Hadoop-AWS options, but provider-specific values and version support vary —
> confirm against your cluster's Hadoop version and the provider's docs.

## S3A configuration for a non-AWS endpoint
- **Endpoint:** `fs.s3a.endpoint` must point at the provider endpoint (e.g. the OSS
  `oss-<region>.aliyuncs.com` / COS / BOS host), not the AWS default.
- **Path-style access:** many non-AWS endpoints need
  `fs.s3a.path.style.access=true` (virtual-hosted style requires bucket DNS the
  provider may not serve). A `Bucket does not exist` / DNS error with a correct
  bucket is the classic symptom of the wrong addressing style.
- **Signing region:** SigV4 signs with a region in the credential scope; a non-AWS
  endpoint rejects a signature scoped to the wrong region. Set the connector's
  region/endpoint consistently (see the OSS signing-region case in the protocol
  skill).
- **Credentials provider:** point `fs.s3a.aws.credentials.provider` at a simple
  access-key provider for static provider keys rather than AWS instance/role
  providers.

## What breaks committers and listings
- **Multipart / ETag:** the S3A committers and any checksum verification assume the
  AWS multipart ETag shape; non-AWS ETags differ (see
  `../../storageops-s3-protocol-compatibility/references/checksum-etag.md`). Do not
  rely on cross-provider ETag equality for commit validation.
- **LIST pagination / delimiter:** continuation-token and delimiter handling can
  differ subtly; very large directory listings are where quirks surface.
- **Committer choice:** the magic committer depends on S3-guarantees the provider
  may implement differently — verify the committer works on a small job before a
  large run, and prefer a staging committer if the magic committer misbehaves.

## Routing
Signature / XML / checksum / endpoint-style errors → involve
`storageops-s3-protocol-compatibility`. Throughput/throttling on listing storms →
`storageops-performance-diagnosis`.
