/**
 * StorageOps Pi Extension — v1.0
 *
 * A lightweight Pi extension that provides object-storage diagnostic tools.
 * All tools run inline in the TypeScript runtime — no Python subprocess.
 *
 * Architecture:
 *   Pi ← storageops.ts (3 tools: scan_secrets, detect_domain, search_memory)
 *     ← skills/*.SKILL.md (15 diagnostic skill packs)
 *
 * Placement: .pi/extensions/storageops.ts (auto-discovered by Pi)
 * Reload:    /reload inside Pi session
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

// ── Secret Scanner ──────────────────────────────────────────────────────────
// Embedded regex patterns for credential detection.
// Patterns match: AWS AK/SK, tokens, Authorization headers, Alibaba/Tencent/Baidu
// Cloud AK/SK, rclone config secrets, private keys.

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
  // Private keys (PEM format)
  [/-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----/g, "PRIVATE_KEY"],
  // rclone config passwords
  [/(?:pass|password|token|secret)[\s]*=[\s]*['"]?([^\s'"]{8,})['"]?/gi, "RCLONE_CREDENTIAL"],
  // Generic API keys (sk-... for OpenAI/DeepSeek style)
  [/(?:api[\s_-]*)?(?:key|token)[\s]*[:=][\s]*['"]?(sk-[A-Za-z0-9]{20,})['"]?/gi, "API_KEY"],
  // GitHub tokens (ghp_, gho_, github_pat_)
  [/(?:ghp_|gho_|github_pat_)[A-Za-z0-9]{36,}/g, "GITHUB_TOKEN"],
];

function redactText(text: string): { findings: Array<{ line: number; type: string; preview: string }>; redacted: string } {
  const findings: Array<{ line: number; type: string; preview: string }> = [];
  let redacted = text;

  for (const [pattern, type] of SECRET_PATTERNS) {
    // Reset lastIndex for global regex
    pattern.lastIndex = 0;
    const matches = Array.from(text.matchAll(pattern));
    for (const m of matches) {
      const line = text.slice(0, m.index!).split("\n").length;
      const preview = m[0].length > 60 ? m[0].slice(0, 60) + "..." : m[0];
      // Skip if already redacted
      if (redacted.includes("[REDACTED]")) {
        const before = redacted.slice(Math.max(0, m.index! - 30), m.index!).toLowerCase();
        const after = redacted.slice(m.index! + m[0].length, m.index! + m[0].length + 30).toLowerCase();
        if (before.includes("[redacted]") || after.includes("[redacted]")) continue;
      }
      findings.push({ line, type, preview });
    }
  }

  // Redact in reverse order to preserve positions
  for (const [pattern] of SECRET_PATTERNS) {
    pattern.lastIndex = 0;
    redacted = redacted.replace(pattern, "[REDACTED]");
  }

  return { findings, redacted };
}


// ── Domain Detection ────────────────────────────────────────────────────────
// Signature-based domain classification from evidence text.
// Replaces the old Python storageops/utils/signatures.py

const DOMAIN_SIGNATURES: Record<string, Array<[RegExp, string]>> = {
  "security-iam-policy": [
    [/403\s*(?:Forbidden|Access\s*Denied)/i, "access_denied"],
    [/AccessDenied/i, "access_denied_api"],
    [/InvalidAccessKeyId/i, "invalid_key"],
    [/SignatureDoesNotMatch/i, "signature_error"],
    [/RequestExpired|clock\s*skew/i, "clock_skew"],
    [/KMS/i, "kms_error"],
    [/Unauthorized/i, "unauthorized"],
    [/AssumeRole|sts:/i, "role_error"],
  ],
  "performance-throttling": [
    [/429|TooManyRequests|RequestRateLimitExceeded/i, "rate_limit"],
    [/SlowDown/i, "slow_down"],
    [/throttl/i, "throttle"],
    [/timeout|timed?\s*out/i, "timeout"],
    [/bandwidth/i, "bandwidth"],
    [/retry/i, "retry"],
  ],
  "network-endpoint": [
    [/DNS|Name\s*or\s*service\s*not\s*known|NXDOMAIN/i, "dns"],
    [/Could\s*not\s*connect|Connection\s*refused|connect\s*ETIMEDOUT/i, "connectivity"],
    [/TLS|SSL|Certificate|cert/i, "tls"],
    [/VPC|endpoint|ENDPOINT/i, "endpoint"],
    [/host\s*unreachable|no\s*route/i, "route"],
  ],
  "cli-sdk": [
    [/rclone/i, "rclone"],
    [/s5cmd/i, "s5cmd"],
    [/awscli|botocore|boto3/i, "aws_cli"],
    [/bcecmd|bos:/i, "bcecmd"],
    [/obsutil|obs:/i, "obsutil"],
    [/corrupted\s*on\s*transfer|multipart.*etag/i, "corruption"],
  ],
  "replication-versioning": [
    [/replicat/i, "replication"],
    [/CRR|SRR/i, "replication_type"],
    [/version/i, "versioning"],
    [/DeleteMarker/i, "delete_marker"],
    [/sync\s*(?:lag|delay)/i, "sync_lag"],
  ],
  "lifecycle-cost": [
    [/lifecycle/i, "lifecycle"],
    [/Standard_IA|Glacier|Deep_Archive/i, "storage_class"],
    [/cost|费用|计费|账单/i, "cost"],
    [/transition|expir/i, "transition"],
    [/objects.*small|small.*objects/i, "small_objects"],
  ],
  "mount-filesystem": [
    [/mount|FUSE|s3fs|goofys/i, "mount"],
    [/fuse|FUSE/i, "fuse"],
    [/filesystem/i, "filesystem"],
  ],
  "migration-sync": [
    [/migrat|搬迁|迁移/i, "migration"],
    [/sync|cp\s+-r/i, "sync"],
    [/transfer/i, "transfer"],
  ],
  "data-consistency": [
    [/consistenc|一致性/i, "consistency"],
    [/stale|陈旧/i, "stale"],
    [/mismatch/i, "mismatch"],
    [/checksum|ETag/i, "checksum"],
  ],
  "event-notification": [
    [/notification|通知/i, "notification"],
    [/event/i, "event"],
  ],
};

function detectDomain(text: string): Array<{ domain: string; confidence: number; subdomains: string[] }> {
  const scores: Record<string, { score: number; subdomains: Set<string> }> = {};

  for (const [domain, patterns] of Object.entries(DOMAIN_SIGNATURES)) {
    for (const [regex, subdomain] of patterns) {
      if (regex.test(text)) {
        if (!scores[domain]) scores[domain] = { score: 0, subdomains: new Set() };
        scores[domain].score += 1;
        scores[domain].subdomains.add(subdomain);
      }
    }
  }

  return Object.entries(scores)
    .map(([domain, info]) => ({
      domain,
      confidence: Math.min(info.score / (DOMAIN_SIGNATURES[domain]?.length || 1), 0.95),
      subdomains: Array.from(info.subdomains),
    }))
    .sort((a, b) => b.confidence - a.confidence);
}


// ── Memory Search ───────────────────────────────────────────────────────────
// Searches Pi session JSONL files for past diagnostic context.

function searchMemory(query: string, limit: number = 5): Array<{ sessionId: string; snippet: string; updated: string }> {
  const sessionsDir = path.join(os.homedir(), ".pi", "agent", "sessions");
  if (!fs.existsSync(sessionsDir)) return [];

  const metaFiles = fs.readdirSync(sessionsDir)
    .filter(f => f.endsWith(".meta.json"))
    .sort()
    .reverse();

  const results: Array<{ sessionId: string; snippet: string; updated: string }> = [];
  const queryLower = query.toLowerCase();

  for (const metaFile of metaFiles) {
    if (results.length >= limit) break;
    try {
      const metaPath = path.join(sessionsDir, metaFile);
      const meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
      const sessionId = meta.id || metaFile.replace(".meta.json", "");

      // Search summary field or read first few JSONL lines
      const summary = meta.summary || meta.name || "";
      if (summary.toLowerCase().includes(queryLower)) {
        results.push({
          sessionId,
          snippet: summary.slice(0, 200),
          updated: meta.updated || meta.created || "",
        });
        continue;
      }

      // Try searching JSONL file
      const jsonlPath = path.join(sessionsDir, `${sessionId}.jsonl`);
      if (fs.existsSync(jsonlPath)) {
        const content = fs.readFileSync(jsonlPath, "utf8").slice(0, 10000); // First 10KB
        if (content.toLowerCase().includes(queryLower)) {
          results.push({
            sessionId,
            snippet: summary.slice(0, 200) || `Session ${sessionId.slice(0, 8)}...`,
            updated: meta.updated || "",
          });
        }
      }
    } catch {
      // Skip unreadable files
    }
  }

  return results;
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

      const { findings, redacted } = redactText(params.text);

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            findings,
            count: findings.length,
            redacted_text: redacted,
          }),
        }],
        details: {
          secretCount: findings.length,
          secretTypes: [...new Set(findings.map(f => f.type))],
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
      "event notification). Returns ranked domains with confidence scores and matched subdomains. " +
      "Use this to quickly identify which diagnostic skill to activate.",
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

      return {
        content: [{
          type: "text",
          text: JSON.stringify({ domains }),
        }],
        details: {
          topDomain: domains[0]?.domain || "unknown",
          topConfidence: domains[0]?.confidence || 0,
          domainCount: domains.length,
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
      "summaries, and timestamps. Use this to find prior diagnoses of similar problems, learn from " +
      "past fixes, or provide continuity across sessions.",
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
