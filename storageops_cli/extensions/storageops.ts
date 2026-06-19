/**
 * StorageOps Pi Extension — v1.0
 *
 * A lightweight Pi extension that provides object-storage diagnostic tools.
 * Most tools run inline in the TypeScript runtime. capture_http_trace may run
 * the external httpmon binary, but only through a bounded, read-only wrapper.
 *
 * Architecture:
 *   Pi ← storageops.ts (4 tools: scan_secrets, detect_domain, search_memory, capture_http_trace)
 *     ← skills/*.SKILL.md (16 packs: 13 diagnostic + triage + reporting + 1 eval)
 *
 * Placement: .pi/extensions/storageops.ts (auto-discovered by Pi)
 * Reload:    /reload inside Pi session
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import * as childProcess from "child_process";

// ── Secret Scanner ──────────────────────────────────────────────────────────
// Embedded regex patterns for credential detection.
// Patterns match: AWS AK/SK, tokens, Authorization headers, Alibaba/Tencent/Baidu
// Cloud AK/SK, rclone config secrets, private keys.

const MAX_SECRET_SCAN_CHARS = 200_000;
const MAX_REDACTED_TEXT_CHARS = 20_000;
const SECRET_PATTERNS: Array<[RegExp, string]> = [
  // AWS access keys (AKIA...)
  [/(?:AWS|aws)[\s_-]*(?:access[\s_-]*)?(?:key[\s_-]*id|akid)[\s]*[:=][\s]*([A-Z0-9]{16,})/gi, "AWS_ACCESS_KEY"],
  [/(?:AKIA|ASIA)[A-Z0-9]{16}/g, "AWS_ACCESS_KEY_ID"],
  // AWS secret keys — long alphanumeric with config keyword
  [/(?:secret[\s_-]*)?(?:access[\s_-]*)?key[\s]*[:=][\s]*['"]?([A-Za-z0-9\/+=]{20,60})['"]?/gi, "AWS_SECRET_KEY"],
  // AWS session tokens
  [/(?:session[\s_-]*)?(?:token|x-amz-security-token)[\s]*[:=][\s]*['"]?([A-Za-z0-9\/+=]{100,})['"]?/gi, "AWS_SESSION_TOKEN"],
  // Alibaba Cloud AK
  [/(?:LTAI)[A-Za-z0-9]{16,20}/g, "ALIBABA_ACCESS_KEY"],
  // Tencent Cloud SecretId
  [/(?:AKID)[A-Za-z0-9]{32,48}/g, "TENCENT_SECRET_ID"],
  // Baidu Cloud AK
  [/(?:ak[\s]*=|access_key[\s]*=)[\s]*['"]?([a-f0-9]{32})['"]?/gi, "BAIDU_ACCESS_KEY"],
  // Generic Authorization: Bearer / Basic tokens
  [/Authorization[\s]*:[\s]*(?:Bearer|Basic|AWS4-HMAC-SHA256)[\s]+([^\s]{20,})/gi, "AUTHORIZATION_HEADER"],
  // SigV4 Authorization headers carry the HMAC after the credential scope, e.g.
  // "Credential=.../s3/aws4_request, Signature=<hex>". Redact the signature value
  // while leaving the credential scope (date/region/service) — useful evidence — visible.
  [/\bSignature=([0-9a-fA-F]{16,})/g, "SIGV4_SIGNATURE"],
  // Private keys (PEM) — incl. plain PKCS8 "PRIVATE KEY" used by GCP service-account keys
  [/-----BEGIN (?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----/g, "PRIVATE_KEY"],
  // rclone config passwords
  [/(?:pass|password|token|secret)[\s]*=[\s]*['"]?([^\s'"]{8,})['"]?/gi, "RCLONE_CREDENTIAL"],
  // Generic API keys (sk-... for OpenAI/DeepSeek style)
  [/(?:api[\s_-]*)?(?:key|token)[\s]*[:=][\s]*['"]?(sk-[A-Za-z0-9]{20,})['"]?/gi, "API_KEY"],
  // GitHub tokens (ghp_, gho_, github_pat_)
  [/(?:ghp_|gho_|github_pat_)[A-Za-z0-9]{36,}/g, "GITHUB_TOKEN"],
  // Presigned-URL signature material — extremely common in rclone/aws/s5cmd debug logs
  [/[?&](?:X-Amz-Signature|X-Goog-Signature)=([A-Za-z0-9%]{16,})/gi, "PRESIGNED_SIGNATURE"],
  [/[?&]X-Amz-(?:Credential|Security-Token)=([^&\s]{16,})/gi, "PRESIGNED_AWS_PARAM"],
  [/[?&](?:OSSAccessKeyId|Signature)=([^&\s]{10,})/gi, "OSS_PRESIGNED"],
  [/[?&]q-(?:signature|ak)=([^&\s]{8,})/gi, "COS_PRESIGNED"],
  // GCP service-account key id (the PEM private_key itself is caught above)
  [/"private_key_id"[\s]*:[\s]*"([a-f0-9]{16,})"/gi, "GCP_PRIVATE_KEY_ID"],
  // Azure storage account key + SAS signature
  [/AccountKey=([A-Za-z0-9+\/=]{40,})/gi, "AZURE_ACCOUNT_KEY"],
  [/[?&]sig=([A-Za-z0-9%]{20,})/gi, "AZURE_SAS"],
];

function secretFingerprint(value: string): string {
  return "sha256:" + crypto.createHash("sha256").update(value).digest("hex").slice(0, 12);
}

type SecretFinding = {
  line: number;
  column: number;
  type: string;
  length: number;
  fingerprint: string;
};

function matchSecretRange(match: RegExpMatchArray): { start: number; end: number; value: string } {
  const matchStart = match.index ?? 0;
  const full = match[0] || "";
  const captured = match.slice(1).find(v => typeof v === "string" && v.length > 0);
  if (captured) {
    const offset = full.lastIndexOf(captured);
    if (offset >= 0) {
      return { start: matchStart + offset, end: matchStart + offset + captured.length, value: captured };
    }
  }
  return { start: matchStart, end: matchStart + full.length, value: full };
}

function lineAndColumn(text: string, index: number): { line: number; column: number } {
  const prefix = text.slice(0, index);
  const line = prefix.split("\n").length;
  const lastNewline = prefix.lastIndexOf("\n");
  return { line, column: index - lastNewline };
}

export function redactText(text: string): { findings: SecretFinding[]; redacted: string; truncated: boolean } {
  const scanText = text.slice(0, MAX_SECRET_SCAN_CHARS);
  const findings: SecretFinding[] = [];
  const ranges: Array<[number, number]> = [];

  for (const [pattern, type] of SECRET_PATTERNS) {
    // Reset lastIndex for global regex
    pattern.lastIndex = 0;
    const matches = Array.from(scanText.matchAll(pattern));
    for (const m of matches) {
      const { start, end, value } = matchSecretRange(m);
      if (ranges.some(([rangeStart, rangeEnd]) => start < rangeEnd && end > rangeStart)) {
        continue;
      }
      const { line, column } = lineAndColumn(scanText, start);
      const length = value.length;
      const fingerprint = secretFingerprint(value);
      ranges.push([start, end]);
      findings.push({ line, column, type, length, fingerprint });
    }
  }

  let redacted = scanText;
  for (const [start, end] of [...ranges].sort((a, b) => b[0] - a[0])) {
    redacted = redacted.slice(0, start) + "[REDACTED]" + redacted.slice(end);
  }

  return {
    findings,
    redacted: redacted.slice(0, MAX_REDACTED_TEXT_CHARS),
    truncated: text.length > scanText.length || redacted.length > MAX_REDACTED_TEXT_CHARS,
  };
}


// ── Domain Detection ────────────────────────────────────────────────────────
// Signature-based domain classification from evidence text.
// Replaces the old Python storageops/utils/signatures.py

const DOMAIN_SIGNATURES: Record<string, Array<[RegExp, string]>> = {
  "storageops-security-iam-policy": [
    [/403\s*(?:Forbidden|Access\s*Denied)/i, "access_denied"],
    [/AccessDenied/i, "access_denied_api"],
    [/InvalidAccessKeyId/i, "invalid_key"],
    [/KMS/i, "kms_error"],
    [/Unauthorized/i, "unauthorized"],
    [/AssumeRole|sts:/i, "role_error"],
    [/权限|无权限|鉴权|拒绝访问|访问被拒/i, "access_denied_cjk"],
  ],
  "storageops-s3-protocol-compatibility": [
    [/SignatureDoesNotMatch|AuthorizationHeaderMalformed|InvalidArgument/i, "signature_or_protocol_error"],
    [/RequestTimeTooSkewed|RequestExpired|NotImplemented|MissingContentLength|EntityTooLarge|EntityTooSmall|PreconditionFailed/i, "protocol_error_code"],
    [/\bBadDigest(?:SHA256|MD5)?\b/i, "payload_digest"],
    [/CanonicalRequest|StringToSign|AWS4-HMAC-SHA256|SigV4|SigV2/i, "signature_debug"],
    [/CORS|preflight|Access-Control-Allow-Origin|Access-Control-Allow-Methods/i, "cors"],
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
    [/cost|费用|计费|账单/i, "cost"],
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
    [/mismatch/i, "mismatch"],
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
};

type DomainDetection = {
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

type ProviderDetection = ProviderEntry & {
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


// ── Memory Search ───────────────────────────────────────────────────────────
// Searches Pi session JSONL files for past diagnostic context.

type MemoryResult = {
  sessionId: string;
  snippet: string;
  updated: string;
  source: "summary" | "jsonl";
  score: number;
};

export function searchTokens(query: string): string[] {
  const ascii = query.toLowerCase().match(/[a-z0-9_\-:.]{3,}/g) || [];
  // CJK queries carry no ASCII word tokens, so the old tokenizer returned [] and
  // recall was empty for Chinese. Emit overlapping bigrams (and single chars for
  // length-1 runs) so Chinese memory searches recall partial matches.
  const cjkTokens: string[] = [];
  for (const run of query.match(/[一-鿿]+/g) || []) {
    if (run.length === 1) cjkTokens.push(run);
    else for (let i = 0; i < run.length - 1; i++) cjkTokens.push(run.slice(i, i + 2));
  }
  return Array.from(new Set([...ascii, ...cjkTokens])).slice(0, 12);
}

function scoreText(text: string, tokens: string[]): number {
  const lower = text.toLowerCase();
  return tokens.reduce((score, token) => score + (lower.includes(token) ? 1 : 0), 0);
}

function safeMemorySnippet(text: string): string {
  return redactText(text.replace(/\s+/g, " ").trim()).redacted.slice(0, 240);
}

const MAX_SESSION_SCAN_DEPTH = 4;
const MAX_SESSION_FILES = 200;

// Pi stores session transcripts under scope subdirectories
// (e.g. sessions/<scope>/<id>.jsonl), so a flat top-level scan misses them.
// Walk the sessions tree with bounded depth/count and index by .jsonl files;
// .meta.json is optional sibling enrichment, not required for recall.
export function collectSessionJsonl(root: string): string[] {
  const found: string[] = [];
  const walk = (dir: string, depth: number): void => {
    if (depth > MAX_SESSION_SCAN_DEPTH || found.length >= MAX_SESSION_FILES) return;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (found.length >= MAX_SESSION_FILES) return;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full, depth + 1);
      } else if (entry.isFile() && entry.name.endsWith(".jsonl")) {
        found.push(full);
      }
    }
  };
  walk(root, 0);
  return found;
}

function readSessionMeta(jsonlPath: string): { sessionId: string; summary: string; updated: string } {
  const sessionId = path.basename(jsonlPath, ".jsonl");
  const metaPath = path.join(path.dirname(jsonlPath), `${sessionId}.meta.json`);
  if (fs.existsSync(metaPath)) {
    try {
      const meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
      return {
        sessionId: meta.id || sessionId,
        summary: meta.summary || meta.name || "",
        updated: meta.updated || meta.created || "",
      };
    } catch {
      // Malformed meta; the jsonl content is still searchable.
    }
  }
  return { sessionId, summary: "", updated: "" };
}

export function searchMemory(query: string, limit: number = 5): MemoryResult[] {
  const agentDir = process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi", "agent");
  const primarySessionsDir = path.join(agentDir, "sessions");
  const fallbackSessionsDir = path.join(os.homedir(), ".pi", "agent", "sessions");
  const sessionsDir = fs.existsSync(primarySessionsDir) ? primarySessionsDir : fallbackSessionsDir;
  if (!fs.existsSync(sessionsDir)) return [];

  const tokens = searchTokens(query);
  if (tokens.length === 0) return [];
  const cappedLimit = Math.min(Math.max(limit || 5, 1), 10);

  const jsonlFiles = collectSessionJsonl(sessionsDir)
    .sort()
    .reverse()
    .slice(0, MAX_SESSION_FILES);

  const results: MemoryResult[] = [];

  for (const jsonlPath of jsonlFiles) {
    try {
      const { sessionId, summary, updated } = readSessionMeta(jsonlPath);

      const summaryScore = summary ? scoreText(summary, tokens) : 0;
      if (summaryScore > 0) {
        results.push({
          sessionId,
          snippet: safeMemorySnippet(summary),
          updated,
          source: "summary",
          score: summaryScore,
        });
      }

      const content = fs.readFileSync(jsonlPath, "utf8").slice(0, 40_000);
      const jsonlScore = scoreText(content, tokens);
      if (jsonlScore > 0) {
        const line = content.split(/\r?\n/).find(x => scoreText(x, tokens) > 0) || summary || `Session ${sessionId.slice(0, 8)}...`;
        results.push({
          sessionId,
          snippet: safeMemorySnippet(line),
          updated,
          source: "jsonl",
          score: jsonlScore,
        });
      }
    } catch {
      // Skip unreadable files
    }
  }

  // Keep only the best-scoring entry per session so one session can't occupy
  // multiple result slots (a session matching in both summary and jsonl would
  // otherwise crowd out other relevant sessions).
  const bestBySession = new Map<string, MemoryResult>();
  for (const r of results) {
    const prev = bestBySession.get(r.sessionId);
    if (!prev || r.score > prev.score) bestBySession.set(r.sessionId, r);
  }

  return Array.from(bestBySession.values())
    .sort((a, b) => b.score - a.score || String(b.updated).localeCompare(String(a.updated)))
    .slice(0, cappedLimit);
}


// ── HTTP Trace Capture ──────────────────────────────────────────────────────
// Bounded wrapper around httpmon. This intentionally exposes only a narrow,
// read-only subset to Pi: no raw HAR, no record files, no replay, and no body
// capture in returned output.

type TraceRequest = {
  id: number;
  method: string;
  url: string;
  host: string;
  headers: Record<string, string>;
};

type TraceResponse = {
  req_id: number;
  status: number;
  headers: Record<string, string>;
  body?: string;
};

const MAX_TRACE_REQUESTS = 20;
const MAX_TRACE_SECONDS = 30;
const MAX_UNKNOWN_TRACE_REQUESTS = 5;
const MAX_UNKNOWN_TRACE_SECONDS = 15;
const MAX_TRACE_COMMAND_ARGS = 40;

const READ_ONLY_AWS_S3API = new Set([
  "head-object",
  "head-bucket",
  "list-objects",
  "list-objects-v2",
  "list-buckets",
  "list-object-versions",
  "list-multipart-uploads",
  "get-bucket-location",
  "get-bucket-versioning",
  "get-bucket-replication",
  "get-bucket-encryption",
  "get-bucket-policy-status",
  "get-bucket-policy",
  "get-bucket-logging",
  "get-bucket-notification-configuration",
  "get-bucket-website",
  "get-bucket-request-payment",
  "get-bucket-ownership-controls",
  "get-bucket-object-lock-configuration",
  "get-public-access-block",
  "get-bucket-cors",
  "get-bucket-lifecycle-configuration",
  "get-bucket-tagging",
  "get-bucket-acl",
  "get-object-attributes",
  "get-object-retention",
  "get-object-legal-hold",
]);

const READ_ONLY_CLIENT_OPS = new Set(["ls", "lsf", "lsd", "stat", "head"]);
const MUTATING_CLIENT_OPS = new Set([
  "rm",
  "rb",
  "mb",
  "mv",
  "cp",
  "sync",
  "copy",
  "delete",
  "purge",
  "move",
]);

const MUTATING_AWS_S3API = new Set([
  "put-object",
  "delete-object",
  "delete-objects",
  "delete-bucket",
  "create-bucket",
  "copy-object",
  "complete-multipart-upload",
  "abort-multipart-upload",
  "restore-object",
  "put-bucket",
  "put-object-acl",
  "put-bucket-acl",
  "put-bucket-policy",
  "delete-bucket-policy",
]);

const KNOWN_TRACE_CLIENTS = new Set(["aws", "curl", "rclone", "s5cmd", "mc", "bcecmd", "obsutil", "s3cmd"]);
const UNKNOWN_MUTATING_TOKENS = new Set([
  "post",
  "put",
  "delete",
  "remove",
  "upload",
  "copy",
  "sync",
  "move",
  "create",
  "update",
  "patch",
  "rm",
  "mv",
  "cp",
]);
const WRITE_HTTP_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

const SIGNED_QUERY_KEYS = [
  "x-amz-signature",
  "x-amz-security-token",
  "x-amz-credential",
  "x-oss-signature",
  "x-oss-credential",
  "ossaccesskeyid",
  "signature",
  "security-token",
];

function normalizeFilterHost(value: string): string {
  const input = (value || "").trim();
  if (!input) return "";
  try {
    if (/^https?:\/\//i.test(input)) {
      return new URL(input).host.toLowerCase();
    }
  } catch {
    return "";
  }
  const host = input.split("/")[0].toLowerCase();
  if (!/^[a-z0-9.-]+(?::\d+)?$/i.test(host)) return "";
  return host;
}

function hasSignedQueryMaterial(command: string[]): boolean {
  const text = command.join(" ").toLowerCase();
  return SIGNED_QUERY_KEYS.some(key => text.includes(key));
}

function firstKnownClientOp(args: string[]): string {
  for (const arg of args.slice(1)) {
    if (READ_ONLY_CLIENT_OPS.has(arg) || MUTATING_CLIENT_OPS.has(arg)) return arg;
  }
  return "";
}

function curlMethod(command: string[], lowered: string[]): string {
  for (let i = 1; i < lowered.length; i += 1) {
    const rawArg = command[i];
    const arg = lowered[i];
    if (rawArg === "-X" || arg === "--request") {
      return (lowered[i + 1] || "get").toUpperCase();
    }
    if (rawArg.startsWith("-X") && rawArg.length > 2) {
      return rawArg.slice(2).toUpperCase();
    }
    if (arg.startsWith("--request=")) {
      return arg.slice("--request=".length).toUpperCase();
    }
  }
  const usesHeadFlag = command.includes("-I") || lowered.includes("--head");
  return usesHeadFlag ? "HEAD" : "GET";
}

function commandHosts(command: string[]): string[] {
  const hosts: string[] = [];
  for (let i = 0; i < command.length; i += 1) {
    const arg = command[i];
    let candidate = arg;
    if (arg === "--url" || arg === "-url") {
      candidate = command[i + 1] || "";
    } else if (arg.startsWith("--url=")) {
      candidate = arg.slice("--url=".length);
    }
    if (!/^https?:\/\//i.test(candidate)) continue;
    try {
      hosts.push(new URL(candidate).host.toLowerCase());
    } catch {
      // Ignore malformed URL-like arguments; the wrapped tool will report them.
    }
  }
  return Array.from(new Set(hosts));
}

function curlHasBodyUploadFlag(command: string[], lowered: string[]): boolean {
  const exactLower = new Set(["--data", "--data-raw", "--data-binary", "--form", "--upload-file"]);
  return command.some((raw, index) => {
    const lower = lowered[index];
    return raw === "-d"
      || raw.startsWith("-d")
      || raw === "-F"
      || raw.startsWith("-F")
      || raw === "-T"
      || raw.startsWith("-T")
      || exactLower.has(lower)
      || lower.startsWith("--data=")
      || lower.startsWith("--data-raw=")
      || lower.startsWith("--data-binary=")
      || lower.startsWith("--form=")
      || lower.startsWith("--upload-file=");
  });
}

function clientPolicyForCommand(command: string[]): "known_adapter" | "unknown_observation" {
  const exe = path.basename(command[0] || "").toLowerCase();
  return KNOWN_TRACE_CLIENTS.has(exe) ? "known_adapter" : "unknown_observation";
}

function explicitHttpWriteMethod(command: string[], lowered: string[]): string {
  for (let i = 1; i < lowered.length; i += 1) {
    const rawArg = command[i];
    const arg = lowered[i];
    if (rawArg === "-X" || arg === "--request" || arg === "--method") {
      const method = (lowered[i + 1] || "").toUpperCase();
      if (WRITE_HTTP_METHODS.has(method)) return method;
    }
    if (rawArg.startsWith("-X") && rawArg.length > 2) {
      const method = rawArg.slice(2).toUpperCase();
      if (WRITE_HTTP_METHODS.has(method)) return method;
    }
    for (const prefix of ["--request=", "--method="]) {
      if (arg.startsWith(prefix)) {
        const method = arg.slice(prefix.length).toUpperCase();
        if (WRITE_HTTP_METHODS.has(method)) return method;
      }
    }
  }
  return "";
}

function suspiciousUnknownToken(command: string[]): string {
  const lowered = command.map(x => x.toLowerCase());
  return lowered.find((arg, index) => index > 0 && UNKNOWN_MUTATING_TOKENS.has(arg)) || "";
}

function validateUnknownTraceCommand(command: string[]): string[] {
  const lowered = command.map(x => x.toLowerCase());
  const method = explicitHttpWriteMethod(command, lowered);
  return method ? [`explicit HTTP write method is not allowed: ${method}`] : [];
}

function operationUnclassified(command: string[]): boolean {
  const exe = path.basename(command[0] || "").toLowerCase();
  const lowered = command.map(x => x.toLowerCase());
  if (!KNOWN_TRACE_CLIENTS.has(exe)) return true;
  if (["rclone", "s5cmd", "mc", "bcecmd", "obsutil", "s3cmd"].includes(exe)) {
    return !firstKnownClientOp(lowered);
  }
  return false;
}

function traceHostMismatch(command: string[], filterHost: string): boolean {
  const hosts = commandHosts(command);
  return hosts.length > 0 && Boolean(filterHost) && !hosts.some(host => host === filterHost);
}

function traceWarningsForCommand(command: string[], filterHost: string): string[] {
  const warnings: string[] = [];
  if (traceHostMismatch(command, filterHost)) {
    warnings.push("command URL host differs from filter_host; trace may capture zero requests");
  }
  const suspicious = suspiciousUnknownToken(command);
  if (!KNOWN_TRACE_CLIENTS.has(path.basename(command[0] || "").toLowerCase()) && suspicious) {
    warnings.push(`unknown client argument looks mutating but will be observed in bounded metadata mode: ${suspicious}`);
  }
  if (operationUnclassified(command)) {
    warnings.push("operation is unclassified; using bounded metadata observation");
  }
  return warnings;
}

export function validateTraceCommand(command: string[], filterHost: string, captureBody: boolean): string[] {
  const errors: string[] = [];
  if (!Array.isArray(command) || command.length === 0) {
    errors.push("command must be a non-empty argv array");
    return errors;
  }
  if (command.length > MAX_TRACE_COMMAND_ARGS) {
    errors.push(`command has too many arguments; max is ${MAX_TRACE_COMMAND_ARGS}`);
  }
  if (!filterHost) {
    errors.push("filter_host is required and must be a host name, not a broad substring");
  }
  if (captureBody) {
    errors.push("capture_body=true is not supported in the safe default tool");
  }
  for (const arg of command) {
    if (typeof arg !== "string" || arg.length === 0) {
      errors.push("all command arguments must be non-empty strings");
      break;
    }
  }
  if (hasSignedQueryMaterial(command)) {
    errors.push("presigned URL material is not accepted by capture_http_trace; provide a redacted trace instead");
  }

  const exe = path.basename(command[0] || "").toLowerCase();
  const lowered = command.map(x => x.toLowerCase());
  const blockedShells = new Set(["sh", "bash", "zsh", "fish", "pwsh", "powershell", "sudo"]);
  if (blockedShells.has(exe)) {
    errors.push("shells and sudo are not allowed for HTTP trace capture");
  }

  if (exe === "aws") {
    const s3api = lowered.indexOf("s3api");
    const s3 = lowered.indexOf("s3");
    if (s3api >= 0) {
      const op = lowered[s3api + 1] || "";
      if (MUTATING_AWS_S3API.has(op)) {
        errors.push(`mutating or high-risk operation is not allowed: ${op}`);
      }
      if (!READ_ONLY_AWS_S3API.has(op)) {
        errors.push(`aws s3api operation is not in the read-only allowlist: ${op || "(missing)"}`);
      }
    } else if (s3 >= 0) {
      const op = lowered[s3 + 1] || "";
      if (op !== "ls") {
        errors.push(`aws s3 operation is not in the read-only allowlist: ${op || "(missing)"}`);
      }
    } else {
      errors.push("aws capture requires an s3 or s3api read-only operation");
    }
  } else if (exe === "curl") {
    const method = curlMethod(command, lowered);
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      errors.push(`curl method is not read-only: ${method}`);
    }
    if (curlHasBodyUploadFlag(command, lowered)) {
      errors.push("curl body upload flags are not allowed");
    }
  } else if (["rclone", "s5cmd", "mc", "bcecmd", "obsutil", "s3cmd"].includes(exe)) {
    const op = firstKnownClientOp(lowered);
    if (MUTATING_CLIENT_OPS.has(op)) {
      errors.push(`mutating or high-risk operation is not allowed: ${op}`);
    }
    if (op && !READ_ONLY_CLIENT_OPS.has(op)) {
      errors.push(`${exe} operation is not in the read-only allowlist: ${op}`);
    }
  } else {
    errors.push(...validateUnknownTraceCommand(command));
  }

  return [...new Set(errors)];
}

const WRITE_REJECTION_MARKERS = [
  "mutating",
  "read-only allowlist",
  "write method",
  "method is not read-only",
];

// When a trace is rejected because the command writes (or is not provably
// read-only), point the agent at the evidence ladder instead of leaving a dead
// end. capture_http_trace executes commands, so tracing a write would perform a
// real request; the request shape is recoverable without re-sending the write.
export function traceRejectionGuidance(errors: string[]): string {
  const isWriteRejection = (errors || []).some(err =>
    WRITE_REJECTION_MARKERS.some(marker => err.toLowerCase().includes(marker)),
  );
  if (!isWriteRejection) return "";
  return (
    "This command writes or is not provably read-only, and capture_http_trace " +
    "executes commands — tracing it would perform a real request. To diagnose a " +
    "failing write, read the server error body and the client's own debug dump " +
    "(aws --debug / rclone -vv --dump headers / boto3 set_stream_logger), then " +
    "recompute offline. See storageops-s3-protocol-compatibility/references/" +
    "checksum-etag.md (Write-side request evidence). Re-run capture_http_trace " +
    "only on a read-only command."
  );
}

function getHeader(headers: Record<string, string> | undefined, name: string): string {
  if (!headers) return "";
  const target = name.toLowerCase();
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === target) return String(value);
  }
  return "";
}

function safePathTemplate(rawURL: string): string {
  try {
    const u = new URL(rawURL);
    const parts = u.pathname.split("/").map(part => {
      if (!part) return part;
      if (part.length > 48) return ":segment";
      if (/^(AKIA|ASIA|AKID|LTAI|sk-)/i.test(part)) return "[REDACTED]";
      if (/^[a-f0-9]{32,}$/i.test(part)) return ":hex";
      return part;
    });
    const capped = parts.length > 7 ? parts.slice(0, 7).concat(["..."]) : parts;
    return capped.join("/") || "/";
  } catch {
    return "/";
  }
}

function parseAuthShape(headers: Record<string, string> | undefined): {
  auth_header_present: boolean;
  auth_scheme?: string;
  signed_headers?: string[];
  credential_scope?: string;
  credential_scope_region?: string;
  credential_scope_service?: string;
} {
  const auth = getHeader(headers, "Authorization");
  if (!auth) return { auth_header_present: false };

  const scheme = auth.split(/\s+/)[0] || "unknown";
  const signed = /SignedHeaders=([^,\s]+)/i.exec(auth)?.[1] || "";
  const credential = /Credential=([^,\s]+)/i.exec(auth)?.[1] || "";
  let scope = "";
  let region = "";
  let service = "";
  if (credential) {
    try {
      const decoded = decodeURIComponent(credential);
      const parts = decoded.split("/");
      if (parts.length >= 5) {
        scope = parts.slice(1).join("/");
        region = parts[2] || "";
        service = parts[3] || "";
      }
    } catch {
      scope = "";
    }
  }
  return {
    auth_header_present: true,
    auth_scheme: scheme,
    signed_headers: signed ? signed.split(/%3B|;/i).filter(Boolean) : [],
    credential_scope: scope || undefined,
    credential_scope_region: region || undefined,
    credential_scope_service: service || undefined,
  };
}

function queryKeySummary(rawURL: string): { has_presigned_query: boolean; query_keys: string[] } {
  try {
    const u = new URL(rawURL);
    const keys = Array.from(new Set(Array.from(u.searchParams.keys()).map(k => k.toLowerCase()))).sort();
    const hasSigned = keys.some(k => SIGNED_QUERY_KEYS.includes(k));
    return { has_presigned_query: hasSigned, query_keys: keys.slice(0, 20) };
  } catch {
    return { has_presigned_query: false, query_keys: [] };
  }
}

function extractS3ErrorCode(body: string | undefined): string | undefined {
  if (!body) return undefined;
  const text = body.slice(0, 4096);
  return /<Code>([^<]{1,80})<\/Code>/i.exec(text)?.[1]
    || /"Code"\s*:\s*"([^"]{1,80})"/i.exec(text)?.[1]
    || /"code"\s*:\s*"([^"]{1,80})"/i.exec(text)?.[1];
}

const SENSITIVE_RESPONSE_HEADERS = new Set([
  "set-cookie",
  "www-authenticate",
  "proxy-authenticate",
  "authorization",
]);
const REDIRECT_HEADERS = new Set(["location", "content-location"]);
const MAX_RESPONSE_HEADERS = 32;
const MAX_HEADER_VALUE_CHARS = 256;

// Surface response metadata (the diagnostic payload) with targeted sanitization:
// known credential-bearing headers (cookies/auth challenges) keep their name but
// have the value masked; redirect targets are redacted of presigned material
// (which can embed a replayable signature); all other headers pass through so
// metadata like ETag, retention-date, SSE, and checksums is not over-redacted.
export function sanitizeResponseHeaders(
  headers: Record<string, string> | undefined,
): Array<{ name: string; value: string }> {
  if (!headers) return [];
  const out: Array<{ name: string; value: string }> = [];
  for (const [rawName, rawValue] of Object.entries(headers)) {
    if (out.length >= MAX_RESPONSE_HEADERS) break;
    const name = rawName.toLowerCase();
    let value = String(rawValue ?? "");
    if (SENSITIVE_RESPONSE_HEADERS.has(name)) {
      value = "[REDACTED]";
    } else if (REDIRECT_HEADERS.has(name)) {
      value = redactText(value).redacted;
    }
    out.push({ name, value: value.slice(0, MAX_HEADER_VALUE_CHARS) });
  }
  return out;
}

export function summarizeTraceRequest(req: TraceRequest, resp?: TraceResponse) {
  const auth = parseAuthShape(req.headers);
  const query = queryKeySummary(req.url);
  let host = req.host || "";
  try {
    host = new URL(req.url).host || host;
  } catch {
    // keep req.host
  }
  return {
    id: req.id,
    method: req.method,
    method_violation: !["GET", "HEAD", "OPTIONS"].includes(String(req.method || "").toUpperCase()),
    host,
    path_template: safePathTemplate(req.url),
    status: resp?.status,
    s3_error_code: extractS3ErrorCode(resp?.body),
    auth_header_present: auth.auth_header_present,
    auth_scheme: auth.auth_scheme,
    signed_headers: auth.signed_headers,
    credential_scope: auth.credential_scope,
    credential_scope_region: auth.credential_scope_region,
    credential_scope_service: auth.credential_scope_service,
    has_presigned_query: query.has_presigned_query,
    query_keys: query.query_keys,
    response_headers: sanitizeResponseHeaders(resp?.headers),
  };
}

function findHttpmonBinary(): string {
  const configured = process.env.STORAGEOPS_HTTPMON;
  if (configured && fs.existsSync(configured)) return configured;
  const managed = path.join(os.homedir(), ".storageops", "bin", process.platform === "win32" ? "httpmon.exe" : "httpmon");
  if (fs.existsSync(managed)) return managed;
  return "httpmon";
}

async function captureHttpTrace(params: {
  command: string[];
  filter_host: string;
  max_requests?: number;
  max_seconds?: number;
  capture_body?: boolean;
}) {
  const filterHost = normalizeFilterHost(params.filter_host || "");
  const clientPolicy = clientPolicyForCommand(params.command || []);
  const warnings = traceWarningsForCommand(params.command || [], filterHost);
  const hostMismatch = traceHostMismatch(params.command || [], filterHost);
  const opUnclassified = operationUnclassified(params.command || []);
  const strictObservation = clientPolicy === "unknown_observation" || opUnclassified;
  const requestCap = strictObservation ? MAX_UNKNOWN_TRACE_REQUESTS : MAX_TRACE_REQUESTS;
  const secondsCap = strictObservation ? MAX_UNKNOWN_TRACE_SECONDS : MAX_TRACE_SECONDS;
  const maxRequests = Math.min(Math.max(Number(params.max_requests || requestCap), 1), requestCap);
  const maxSeconds = Math.min(Math.max(Number(params.max_seconds || secondsCap), 1), secondsCap);
  const captureBody = Boolean(params.capture_body);
  const validationErrors = validateTraceCommand(params.command, filterHost, captureBody);
  if (validationErrors.length > 0) {
    return {
      status: "rejected",
      reason: "unsafe_or_unsupported_command",
      client_policy: clientPolicy,
      warnings,
      host_mismatch: hostMismatch,
      operation_unclassified: opUnclassified,
      errors: validationErrors,
      guidance: traceRejectionGuidance(validationErrors) || undefined,
      limits: { max_requests: maxRequests, max_seconds: maxSeconds, capture_body: false },
    };
  }

  return new Promise(resolve => {
    const httpmonBinary = findHttpmonBinary();
    const httpmon = childProcess.spawn(
      httpmonBinary,
      ["--format", "json", "--filter", filterHost, ...params.command],
      { stdio: ["ignore", "pipe", "pipe"] },
    );

    const requests = new Map<number, TraceRequest>();
    const responses = new Map<number, TraceResponse>();
    let buffer = "";
    let stderr = "";
    let killedForLimit = false;
    let spawnError = "";
    let finished = false;

    const finish = (exitCode: number | null) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      const summaries = Array.from(requests.values())
        .slice(0, maxRequests)
        .map(req => summarizeTraceRequest(req, responses.get(req.id)));
      const redactedStderr = redactText(stderr.slice(0, 2000)).redacted;
      resolve({
        status: spawnError ? "error" : "completed",
        command_name: path.basename(params.command[0]),
        client_policy: clientPolicy,
        warnings,
        host_mismatch: hostMismatch,
        operation_unclassified: opUnclassified,
        filter_host: filterHost,
        exit_code: exitCode,
        killed_for_limit: killedForLimit,
        requests: summaries,
        request_count: summaries.length,
        method_violation: summaries.some((r: any) => r.method_violation),
        stderr_summary: redactedStderr.slice(0, 500),
        redaction: {
          authorization_redacted: summaries.some((r: any) => r.auth_header_present),
          presigned_query_redacted: summaries.some((r: any) => r.has_presigned_query),
          response_headers_sanitized: true,
          body_captured: false,
          raw_trace_saved: false,
          har_saved: false,
          replay_performed: false,
        },
        limits: { max_requests: maxRequests, max_seconds: maxSeconds, capture_body: false },
        error: spawnError || undefined,
      });
    };

    const handleLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed.startsWith("{")) return;
      try {
        const event = JSON.parse(trimmed);
        if (typeof event.id === "number" && typeof event.method === "string" && typeof event.url === "string") {
          requests.set(event.id, {
            id: event.id,
            method: event.method,
            url: event.url,
            host: event.host || "",
            headers: event.headers || {},
          });
          if (requests.size >= maxRequests && httpmon.pid) {
            killedForLimit = true;
            httpmon.kill("SIGTERM");
          }
        } else if (typeof event.req_id === "number" && typeof event.status === "number") {
          responses.set(event.req_id, {
            req_id: event.req_id,
            status: event.status,
            headers: event.headers || {},
            body: event.body || "",
          });
        }
      } catch {
        // Ignore subprocess output that is not httpmon NDJSON.
      }
    };

    const timer = setTimeout(() => {
      killedForLimit = true;
      if (httpmon.pid) httpmon.kill("SIGTERM");
    }, maxSeconds * 1000);

    httpmon.stdout?.on("data", chunk => {
      buffer += chunk.toString("utf8");
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) handleLine(line);
    });
    httpmon.stderr?.on("data", chunk => {
      stderr += chunk.toString("utf8");
    });
    httpmon.on("error", err => {
      spawnError = err.message || String(err);
      finish(null);
    });
    httpmon.on("close", code => {
      if (buffer.trim()) handleLine(buffer);
      finish(code);
    });
  });
}


// ── Extension Entry Point ───────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ── Tool: scan_secrets ──
  pi.registerTool({
    name: "scan_secrets",
    label: "Scan Secrets",
    description:
      "Scan text for exposed credentials and redact them. Detects AWS access keys (AKIA...), " +
      "session tokens, Authorization headers, Alibaba/Tencent/Baidu Cloud AK/SK, rclone config " +
      "secrets, private keys, and API tokens. Returns a findings list and the redacted text. " +
      "Always call BEFORE passing any user-provided text to other tools or including it in responses.",
    parameters: Type.Object({
      text: Type.String({ description: "Text to scan for secrets" }),
    }),
    async execute(_toolCallId, params) {
      if (!params.text || params.text.length === 0) {
        return {
          content: [{ type: "text", text: JSON.stringify({ findings: [], count: 0, redacted_text: "" }) }],
          details: {},
        };
      }

      const scan = redactText(params.text);

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            findings: scan.findings,
            count: scan.findings.length,
            redacted_text: scan.redacted,
            truncated: scan.truncated,
          }),
        }],
        details: {
          secretCount: scan.findings.length,
          secretTypes: [...new Set(scan.findings.map(f => f.type))],
          truncated: scan.truncated,
        },
      };
    },
  });

  // ── Tool: detect_domain ──
  pi.registerTool({
    name: "detect_domain",
    label: "Detect Domain",
    description:
      "Analyze evidence text and classify the issue domain (e.g., security, performance, network, " +
      "CLI/SDK, replication, lifecycle/cost, mount/filesystem, migration, data consistency, " +
      "event notification). Returns ranked domains with confidence scores, matched signals, " +
      "recommended skill names, the next evidence action, and a best-effort storage provider " +
      "(aws/bos/oss/cos/gcs/azure/obs/minio) detected from endpoint/headers/CLI with a quirks reference.",
    parameters: Type.Object({
      text: Type.String({ description: "Evidence text to analyze (log output, error messages, user report)" }),
    }),
    async execute(_toolCallId, params) {
      if (!params.text || params.text.length === 0) {
        return {
          content: [{ type: "text", text: JSON.stringify({ domains: [], note: "No text provided" }) }],
          details: {},
        };
      }

      const domains = detectDomain(params.text);
      const provider = detectProvider(params.text);

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            domains,
            recommended_skill: domains[0]?.recommended_skill || null,
            ambiguous: domains.length > 1 && Math.abs(domains[0].confidence - domains[1].confidence) < 0.1,
            provider: provider.provider,
            provider_confidence: provider.confidence,
            provider_signals: provider.signals,
            provider_quirks_ref: provider.quirks_ref,
            providers: provider.providers,
            provider_note: provider.provider === "unknown"
              ? "Provider not identified from the evidence; ask for the endpoint or a response header."
              : provider.providers.length > 1
                ? "Multiple providers detected (e.g. a migration/sync): apply EACH provider's quirks to its side (source vs destination), not one provider's rules to both. Hints to verify — endpoints can be proxied/CNAME'd."
                : "Detected provider is a hint — verify it (endpoints can be proxied/CNAME'd) before applying provider quirks.",
          }),
        }],
        details: {
          topDomain: domains[0]?.domain || "unknown",
          recommendedSkill: domains[0]?.recommended_skill || "unknown",
          topConfidence: domains[0]?.confidence || 0,
          domainCount: domains.length,
          provider: provider.provider,
        },
      };
    },
  });

  // ── Tool: search_memory ──
  pi.registerTool({
    name: "search_memory",
    label: "Search Memory",
    description:
      "Search past StorageOps diagnostic sessions for similar issues. Returns matching session IDs, " +
      "redacted snippets, timestamps, and match scores. Use this to find prior diagnoses without " +
      "leaking credentials from old logs.",
    parameters: Type.Object({
      query: Type.String({ description: "Search query (error code, symptom, tool name, etc.)" }),
      limit: Type.Optional(Type.Number({ description: "Maximum results (default 5)", default: 5 })),
    }),
    async execute(_toolCallId, params) {
      const query = params.query || "";
      const limit = typeof params.limit === "number" ? params.limit : 5;

      if (!query.trim()) {
        return {
          content: [{ type: "text", text: JSON.stringify({ results: [], note: "Empty query" }) }],
          details: {},
        };
      }

      const results = searchMemory(query, limit);

      return {
        content: [{
          type: "text",
          text: JSON.stringify({ results, query }),
        }],
        details: {
          resultCount: results.length,
        },
      };
    },
  });

  // ── Tool: capture_http_trace ──
  pi.registerTool({
    name: "capture_http_trace",
    label: "Capture HTTP Trace",
    description:
      "Run one bounded, read-only object-storage diagnostic command through httpmon and return a " +
      "sanitized HTTP summary. This tool is manual-confirmation oriented: it rejects mutating " +
      "commands, shell strings, presigned URL material, body capture, raw HAR/record output, and " +
      "replay. Use when headers/status/timing would materially improve diagnosis.",
    parameters: Type.Object({
      command: Type.Array(Type.String(), {
        description: "Command argv array to wrap, e.g. ['aws','s3api','head-object','--bucket','b','--key','k']",
      }),
      filter_host: Type.String({ description: "Required host filter, e.g. s3.example.com" }),
      max_requests: Type.Optional(Type.Number({ description: "Maximum captured requests, capped at 20", default: 20 })),
      max_seconds: Type.Optional(Type.Number({ description: "Maximum runtime seconds, capped at 30", default: 30 })),
      capture_body: Type.Optional(Type.Boolean({ description: "Unsafe in P0; must be false", default: false })),
    }),
    async execute(_toolCallId, params) {
      const result = await captureHttpTrace({
        command: Array.isArray(params.command) ? params.command : [],
        filter_host: params.filter_host || "",
        max_requests: params.max_requests,
        max_seconds: params.max_seconds,
        capture_body: params.capture_body,
      });
      return {
        content: [{
          type: "text",
          text: JSON.stringify(result),
        }],
        details: {
          status: (result as any).status,
          requestCount: (result as any).request_count || 0,
        },
      };
    },
  });

  // ── Session startup: log available skills ──
  pi.on("session_start", async (_event, ctx) => {
    const skillsDir = path.resolve(__dirname, "..", "..", "skills");
    if (fs.existsSync(skillsDir)) {
      const skillNames = fs.readdirSync(skillsDir)
        .filter(f => fs.statSync(path.join(skillsDir, f)).isDirectory())
        .sort();
      ctx.logger?.log(`StorageOps: ${skillNames.length} skill packs loaded (${skillNames.join(", ")})`);
    }
  });
}
