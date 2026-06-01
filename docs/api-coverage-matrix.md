# API and Capability Coverage

StorageOps diagnoses failure modes around object storage APIs rather than implementing API clients. Coverage means the skill pack has enough routing, references, scripts, or golden cases to reason about that operation.

## Strong Coverage

| Area | Skills |
| --- | --- |
| `GetObject`, `PutObject`, `HeadObject` | security, performance, protocol, CLI/SDK, data consistency |
| multipart upload and ETag behavior | protocol, CLI/SDK, data consistency |
| SigV4 and signature mismatch | protocol, CLI/SDK, security |
| CORS | protocol |
| AccessDenied and KMS deny | security |
| 429/SlowDown and hot prefixes | performance |
| DNS/TCP/TLS endpoint failures | network |
| lifecycle transitions and request-cost amplification | lifecycle-cost |
| replication, delete markers, object lock | replication-versioning |
| access log spikes and requester attribution | access-log-analysis |

## Partial Coverage

| Area | Current state |
| --- | --- |
| bucket ACL and public access block changes | diagnosed as security policy behavior; no dedicated helper |
| bucket encryption configuration | KMS diagnosis exists; encryption config references are thinner |
| restore/archive retrieval | lifecycle skill can reason about it; no focused golden case yet |
| bucket website hosting | no dedicated skill |
| bucket logging configuration | access-log skill covers log interpretation more than setup |
| static website routing errors | usually out of scope unless expressed as S3/CORS/endpoint issue |

## Explicit Non-Goals

StorageOps does not:

- call cloud APIs with user credentials,
- mutate buckets,
- repair policies automatically,
- serve as a full S3 SDK conformance tester.

## How To Improve Coverage

Add coverage in this order:

1. compact golden case,
2. reference note,
3. deterministic helper if the reasoning can be parsed or measured,
4. SKILL.md routing/workflow update.
