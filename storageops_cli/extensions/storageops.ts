/**
 * StorageOps Pi Extension — entry point and public re-exports.
 * Implementation lives in secrets.ts, routing.ts, memory.ts, and trace.ts.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import * as fs from "fs";
import * as path from "path";

export { redactText } from "./secrets.ts";
export type { SecretFinding } from "./secrets.ts";
export { detectDomain, detectProvider } from "./routing.ts";
export type { DomainDetection, ProviderDetection } from "./routing.ts";
export { searchTokens, searchMemory, collectSessionJsonl } from "./memory.ts";
export type { MemoryResult } from "./memory.ts";
export {
  validateTraceCommand,
  traceRejectionGuidance,
  sanitizeResponseHeaders,
  summarizeTraceRequest,
} from "./trace.ts";

import { redactText } from "./secrets.ts";
import { detectDomain, detectProvider } from "./routing.ts";
import { searchMemory } from "./memory.ts";
import { captureHttpTrace } from "./trace.ts";

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
