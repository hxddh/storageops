// ── Domain Detection ────────────────────────────────────────────────────────
// Signature-based domain classification from evidence text.
// Replaces the old Python storageops/utils/signatures.py

const DOMAIN_SIGNATURES: Record<string, Array<[RegExp, string]>> = {
  "storageops-security-iam-policy": [
    [/403\s*(?:Forbidden|Access\s*Denied)/i, "access_denied"],
    [/AccessDenied/i, "access_denied_api"],
    [/InvalidAccessKeyId/i, "invalid_key"],
    [/kms:\w|\bKMS\b.*\b(key|encrypt|decrypt|SSE|cipher|grant|CMK|GenerateDataKey)\b|\b(key|encrypt|decrypt|SSE|cipher|CMK)\b.*\bKMS\b/i, "kms_error"],
    [/401\s*Unauthorized|\bUnauthorized\b.*\b(request|access|operation|principal|credential|token|user|role|perform|API|HTTP|header|signature)\b|\b(request|access|operation|principal|credential|token|HTTP|API|signature)\b.*\bUnauthorized\b/i, "unauthorized"],
    [/AssumeRole|sts:/i, "role_error"],
    [/权限|无权限|鉴权|拒绝访问|访问被拒/i, "access_denied_cjk"],
  ],
  "storageops-s3-protocol-compatibility": [
    [/SignatureDoesNotMatch|AuthorizationHeaderMalformed|InvalidArgument/i, "signature_or_protocol_error"],
    [/RequestTimeTooSkewed|RequestExpired|NotImplemented|MissingContentLength|EntityTooLarge|EntityTooSmall|PreconditionFailed/i, "protocol_error_code"],
    [/\bBadDigest(?:SHA256|MD5)?\b/i, "payload_digest"],
    [/CanonicalRequest|StringToSign|AWS4-HMAC-SHA256|SigV4|SigV2/i, "signature_debug"],
    [/Access-Control-Allow-Origin|Access-Control-Allow-Methods|NoSuchCORSConfiguration|blocked by CORS policy|\bCORS policy\b.*\b(?:blocked|Origin|preflight|Allow)\b|\bpreflight\b.*\b(?:403|OPTIONS|failed|missing)\b/i, "cors"],
    [/MalformedXML|InvalidDigest|Content-MD5|x-(?:amz|bce)-content-sha256/i, "protocol_header"],
    [/virtual.?hosted|path.?style|chunked|STREAMING-AWS4-HMAC-SHA256-PAYLOAD/i, "provider_compatibility"],
    [/签名|校验和|校验值/i, "signature_or_protocol_cjk"],
  ],
  "storageops-performance-diagnosis": [
    [/429|TooManyRequests|RequestRateLimitExceeded/i, "rate_limit"],
    [/SlowDown/i, "slow_down"],
    [/throttl/i, "throttle"],
    [/timeout|timed?\s*out/i, "timeout"],
    [/bandwidth/i, "bandwidth"],
    [/retry/i, "retry"],
    [/限速|限流|超时|慢|带宽/i, "performance_cjk"],
  ],
  "storageops-network-endpoint-access": [
    [/DNS|Name\s*or\s*service\s*not\s*known|NXDOMAIN/i, "dns"],
    [/Could\s*not\s*connect|Connection\s*refused|connect\s*ETIMEDOUT/i, "connectivity"],
    [/TLS|SSL|\bcert(?:ificate)?\b/i, "tls"],
    [/连接(?:失败|超时|被拒)|证书|解析失败|无法访问/i, "network_cjk"],
    [/VPC|endpoint|ENDPOINT/i, "endpoint"],
    [/host\s*unreachable|no\s*route/i, "route"],
    [/RequestTimeout|connection\s*reset|reset\s*by\s*peer|broken\s*pipe|\bECONNRESET\b|\bEPIPE\b|unexpected\s*EOF/i, "transport"],
  ],
  "storageops-cli-sdk-diagnosis": [
    [/rclone/i, "rclone"],
    [/s5cmd/i, "s5cmd"],
    [/awscli|botocore|boto3/i, "aws_cli"],
    [/\bbcecmd\b|\bgo-bcecli\b/i, "bcecmd"],
    [/\bobsutil\b|\bobs:\/\//i, "obsutil"],
    [/corrupted\s*on\s*transfer|multipart.*etag/i, "corruption"],
    [/损坏|校验失败|传输失败/i, "corruption_cjk"],
  ],
  "storageops-replication-versioning": [
    [/replicat/i, "replication"],
    [/CRR|SRR/i, "replication_type"],
    [/\bversioning\b|version\s*id/i, "versioning"],
    [/DeleteMarker/i, "delete_marker"],
    [/sync\s*(?:lag|delay)/i, "sync_lag"],
  ],
  "storageops-lifecycle-cost": [
    [/lifecycle/i, "lifecycle"],
    [/Standard_IA|Glacier|Deep_Archive/i, "storage_class"],
    [/\bcost\b.*\b(storage|request|egress|transition|tier|bill|lifecycle|retrieval|IA|Glacier|Archive|GB|TB)\b|\b(storage|request|egress|transition|tier|bill|lifecycle|retrieval|IA|Glacier|Archive|GB|TB)\b.*\bcost\b|费用|计费|账单/i, "cost"],
    [/transition|\bexpir(?:e|es|ed|ation|ing)?\b/i, "transition"],
    [/objects.*small|small.*objects/i, "small_objects"],
  ],
  "storageops-mount-filesystem-workspace": [
    [/\bmount(?:ed|ing)?\b|\bFUSE\b|\bs3fs\b|\bgoofys\b/i, "mount"],
    [/\bFUSE\b/i, "fuse"],
    [/\bfilesystem\b/i, "filesystem"],
  ],
  "storageops-migration-sync": [
    [/migrat|搬迁|迁移/i, "migration"],
    [/\b(?:rclone|s5cmd|obsutil|bcecmd|ossutil|coscli)\s+sync\b|\baws\s+s3\s+sync\b|\bmc\s+mirror\b|\bsync\b.*\b(?:s3|oss|cos|obs|bos|bucket|object|prefix|remote:|provider|checksum|verify|verification)\b|\b(?:s3|oss|cos|obs|bos|bucket|object|prefix|remote:|provider)\b.*\bsync\b|cp\s+-r/i, "sync"],
    [/\btransfer(?:s|red|ring)?\b.*\b(?:s3|oss|cos|obs|bos|bucket|object|prefix|provider|cross-region|multipart)\b|\b(?:s3|oss|cos|obs|bos|bucket|object|prefix|provider|cross-region|multipart)\b.*\btransfer(?:s|red|ring)?\b/i, "transfer"],
  ],
  "storageops-data-consistency": [
    [/consistenc|一致性/i, "consistency"],
    [/stale|陈旧/i, "stale"],
    [/\bmismatch\b.*\b(etag|checksum|hash|md5|sha|content|object|data|digest|size|byte)\b|\b(etag|checksum|hash|md5|sha|content|object|data|digest)\b.*\bmismatch\b/i, "mismatch"],
    [/checksum|ETag/i, "checksum"],
  ],
  "storageops-bigdata-pipeline": [
    [/\b(?:Spark|Hive|Flink|Hadoop|S3A|EMR)\b/i, "bigdata_engine"],
    [/FileOutputCommitter|MagicCommitter|S3ACommitter|_temporary|speculative execution/i, "committer"],
    [/partition|Parquet|Iceberg|Delta|Hudi/i, "table_or_partition"],
    [/small files|many files|listing storm|listObjects/i, "small_file_query"],
  ],
  "storageops-event-notification": [
    [/notification|通知/i, "notification"],
    [/event\s*notifications?|bucket\s*events?|\bSQS\b|\bLambda\b/i, "event"],
    [/prefix filter|suffix filter|ObjectCreated|ObjectRemoved/i, "event_filter"],
  ],
  "storageops-access-log-analysis": [
    [/access\s*log|server\s*access\s*log/i, "access_log"],
    [/log\s*(?:analysis|分析)|request\s*analysis|traffic\s*analysis/i, "log_analysis"],
    [/403\s*spike|503\s*spike|error\s*rate|错误率/i, "error_spike"],
    [/who\s+is\s+accessing|top\s*requester|requester/i, "requester"],
    [/cost\s*attribution|费用归因|成本归因/i, "cost_attribution"],
  ],
  "storageops-triage": [
    [/\bobject storage\b|\bS3 error\b|\bstorage issue\b|\bstorage problem\b|\bbucket issue\b/i, "triage_vague"],
    [/uploads?\s+(?:sometimes\s+)?fail|\bno error logs\b|\bno request id\b/i, "triage_incomplete"],
  ],
};

export type DomainDetection = {
  domain: string;
  recommended_skill: string;
  confidence: number;
  subdomains: string[];
  signals: string[];
  next_action: string;
};

// ── Provider Detection ──────────────────────────────────────────────────────
// Object-storage misdiagnosis is dominated by applying AWS assumptions to a
// non-AWS provider. Identify the provider deterministically from endpoint hosts,
// vendor header prefixes, vendor CLIs, and URI schemes — so provider-specific
// quirks get applied even when the user never names the provider. Conservative:
// returns "unknown" unless a clear signal is present. Note: x-amz-* headers are
// shared by all S3-compatible providers, so they are NOT an AWS signal.

type ProviderEntry = {
  provider: string;
  confidence: "high" | "medium" | "low";
  signals: string[];
  quirks_ref: string | null;
};

export type ProviderDetection = ProviderEntry & {
  // All providers detected in the evidence, strongest first. For migration/sync
  // the source and destination differ and need different quirks; the top-level
  // fields are the primary (strongest) provider for backward compatibility.
  providers: ProviderEntry[];
};

const PROVIDER_SIGNATURES: Array<[string, RegExp, string]> = [
  ["aws", /\.amazonaws\.com\b/i, "endpoint:amazonaws.com"],
  ["bos", /\.bcebos\.com\b/i, "endpoint:bcebos.com"],
  ["bos", /x-bce-|\bbcecmd\b|\bgo-bcecli\b|\bbos:\/\//i, "header/cli:bce"],
  ["oss", /\.aliyuncs\.com\b/i, "endpoint:aliyuncs.com"],
  ["oss", /x-oss-|\bossutil\b|\boss:\/\//i, "header/cli:oss"],
  ["cos", /\.myqcloud\.com\b/i, "endpoint:myqcloud.com"],
  ["cos", /x-cos-|\bcoscli\b|\bcoscmd\b|q-sign-algorithm|\bcos:\/\//i, "header/cli:cos"],
  ["gcs", /storage\.googleapis\.com\b/i, "endpoint:googleapis.com"],
  ["gcs", /x-goog-|\bgsutil\b|\bgs:\/\//i, "header/cli:goog"],
  ["azure", /\.blob\.core\.windows\.net\b/i, "endpoint:blob.core.windows.net"],
  ["azure", /x-ms-(?:blob|version|date|meta)|\baz\s+storage\b/i, "header/cli:azure"],
  ["obs", /\.myhuaweicloud\.com\b|\bobs\.[a-z0-9-]+\.myhuaweicloud/i, "endpoint:myhuaweicloud.com"],
  ["obs", /x-obs-|\bobsutil\b|\bobs:\/\//i, "header/cli:obs"],
  ["minio", /\bMinIO\b|x-minio-/i, "marker:minio"],
];

const PROVIDER_QUIRKS_REF: Record<string, string> = {
  bos: "storageops-s3-protocol-compatibility/references/provider-quirks/bos.md",
  oss: "storageops-s3-protocol-compatibility/references/provider-quirks/oss.md",
  cos: "storageops-s3-protocol-compatibility/references/provider-quirks/cos.md",
  minio: "storageops-s3-protocol-compatibility/references/provider-quirks/minio.md",
};

export function detectProvider(text: string): ProviderDetection {
  const evidence = (text || "").slice(0, 100_000);
  const hits: Record<string, string[]> = {};
  for (const [provider, regex, label] of PROVIDER_SIGNATURES) {
    regex.lastIndex = 0;
    if (regex.test(evidence)) (hits[provider] ||= []).push(label);
  }
  const names = Object.keys(hits);
  if (names.length === 0) {
    return { provider: "unknown", confidence: "low", signals: [], quirks_ref: null, providers: [] };
  }
  // Strongest provider = most signal hits; an endpoint host match is high confidence.
  names.sort((a, b) => hits[b].length - hits[a].length);
  const providers: ProviderEntry[] = names.map(name => ({
    provider: name,
    confidence: hits[name].some(l => l.startsWith("endpoint:")) ? "high" : "medium",
    signals: hits[name].map(l => `${name}:${l}`),
    quirks_ref: PROVIDER_QUIRKS_REF[name] ?? null,
  }));
  const primary = providers[0];
  return {
    provider: primary.provider,
    confidence: primary.confidence,
    signals: providers.flatMap(p => p.signals),
    quirks_ref: primary.quirks_ref,
    providers,
  };
}

const DOMAIN_NEXT_ACTION: Record<string, string> = {
  "storageops-security-iam-policy": "Check identity, policy, key validity, bucket policy, and KMS constraints before changing permissions.",
  "storageops-s3-protocol-compatibility": "Compare endpoint style, region, canonical request shape, signing version, and required headers.",
  "storageops-performance-diagnosis": "Separate service throttling, client retry behavior, network latency, and object layout signals.",
  "storageops-network-endpoint-access": "Verify DNS, endpoint, route, proxy, and TLS certificate evidence before testing application logic.",
  "storageops-cli-sdk-diagnosis": "Confirm the exact CLI/SDK, config path, provider, endpoint, and version before applying reference docs.",
  "storageops-replication-versioning": "Inspect versioning, delete markers, replication rules, and observed replication lag.",
  "storageops-lifecycle-cost": "Check lifecycle rules, storage class transitions, request patterns, and dated pricing references.",
  "storageops-mount-filesystem-workspace": "Treat mount tools as filesystem adapters; verify cache, FUSE, permissions, and consistency expectations.",
  "storageops-migration-sync": "Verify read-only inventory, delta strategy, checksums, and idempotent sync planning.",
  "storageops-data-consistency": "Collect timestamps, ETags/checksums, list/head differences, and cross-client observations.",
  "storageops-bigdata-pipeline": "Inspect engine, committer, partition layout, speculative execution, and object-listing behavior.",
  "storageops-event-notification": "Check event rules, prefix/suffix filters, target permissions, and delivery logs.",
  "storageops-access-log-analysis": "Summarize request IDs, status spikes, top requesters, user agents, and time windows.",
  "storageops-triage": "Classify the domain, list evidence gaps, and route to one specialist skill before deep diagnosis.",
};

export function detectDomain(text: string): DomainDetection[] {
  const scores: Record<string, { score: number; subdomains: Set<string>; signals: string[] }> = {};
  const evidence = text.slice(0, 100_000);

  for (const [domain, patterns] of Object.entries(DOMAIN_SIGNATURES)) {
    for (const [regex, subdomain] of patterns) {
      regex.lastIndex = 0;
      const match = regex.exec(evidence);
      if (match) {
        if (!scores[domain]) scores[domain] = { score: 0, subdomains: new Set(), signals: [] };
        scores[domain].score += 1;
        scores[domain].subdomains.add(subdomain);
        scores[domain].signals.push(match[0].slice(0, 80));
      }
    }
  }

  return Object.entries(scores)
    .map(([domain, info]) => ({
      domain,
      recommended_skill: domain,
      confidence: Math.min(0.5 + info.score * 0.15, 0.95),
      subdomains: Array.from(info.subdomains),
      signals: info.signals.slice(0, 5),
      next_action: DOMAIN_NEXT_ACTION[domain] || "Collect more evidence before choosing a specialized skill.",
    }))
    .sort((a, b) => b.confidence - a.confidence);
}
