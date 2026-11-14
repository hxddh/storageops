/**
 * StorageOps 2.0 — Pi extension entry point.
 *
 * Tools are read-only by construction: probes call GET/HEAD, analyzers run
 * allowlisted scripts without a shell, and a diagnosis must cite evidence ids
 * produced in this session. The launcher additionally removes Pi's built-in
 * write tools (see storageops_cli/__init__.py).
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import * as fs from "fs";
import * as path from "path";
import * as childProcess from "child_process";

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
export { signRequest, parseIniProfile, credentialLabel } from "./sigv4.ts";
export { deriveFacts, parseTarget, probeBucket, probeCapabilities, probeEndpoint } from "./probe.ts";
export { registerEvidence, hasEvidence, listEvidence, resetEvidence } from "./evidence.ts";
export type { EvidenceEntry } from "./evidence.ts";
export { validateDiagnosis, renderDiagnosis, resolveRootCause, domainForRoute, routes } from "./diagnosis.ts";
export type { Diagnosis, DiagnosisInput } from "./diagnosis.ts";
export { searchCases, listCases, recordCase, casesDir } from "./cases.ts";
export type { CaseRecord } from "./cases.ts";
export { CONTRACT_VERSION, DOMAINS } from "./contract.generated.ts";

import { redactText } from "./secrets.ts";
import { detectDomain, detectProvider } from "./routing.ts";
import { searchCases } from "./cases.ts";
import { captureHttpTrace } from "./trace.ts";
import { probeBucket, probeCapabilities, probeEndpoint } from "./probe.ts";
import { listEvidence, registerEvidence } from "./evidence.ts";
import { recordCase } from "./cases.ts";
import { routes, validateDiagnosis, domainForRoute, type DiagnosisInput } from "./diagnosis.ts";
import { DOMAINS } from "./contract.generated.ts";
import { credentialLabel, resolveCredentials } from "./sigv4.ts";

const WRITE_TOOLS = new Set(["bash", "powershell", "edit", "write"]);

const CREDENTIAL_PATHS =
  /(^|\/)(\.aws\/(credentials|config)|\.bce\/credentials|\.ossutilconfig|\.rclone\.conf|\.netrc|\.cos\.conf|id_rsa|id_ed25519|api-key)$/i;

const PERSONA = [
  "You are StorageOps, an object-storage diagnostic engineer for S3-compatible storage",
  "(AWS S3, Baidu BOS, Alibaba OSS, Tencent COS, Huawei OBS, MinIO, Ceph RGW, Cloudflare R2, GCS interop).",
  "",
  "Operating rules:",
  "1. Evidence before conclusion. Use probe_endpoint, probe_bucket, probe_capabilities, run_analyzer,",
  "   and capture_http_trace (read-only) to gather facts; do not infer a bucket policy, CORS rule,",
  "   lifecycle rule, or clock state you have not looked at when a probe can check it.",
  "2. Never ask the user to paste credentials, and never repeat a secret. Red action already happened",
  "   before you saw the input; fingerprints are safe to quote.",
  "3. Prefer the cheapest discriminating check: a HEAD beats a full listing, a policy status beats a policy read.",
  "4. Distinguish what you observed from what you inferred. If evidence is insufficient, say exactly which",
  "   probe or artifact would settle it instead of guessing.",
  "5. Finish every diagnosis with submit_diagnosis: root cause from the contract, evidence ids for each claim,",
  "   falsifiers, and manual-only remediation. Do not claim completion without it.",
  "6. Never change infrastructure. StorageOps produces plans a human applies.",
].join("\n");

function evidenceSummary(label: string, facts: Record<string, unknown>): string {
  return `${label}: ${JSON.stringify(facts).slice(0, 560)}`;
}

function skillsDir(): string {
  return path.resolve(__dirname, "..", "..", "skills");
}

function analyzerPath(name: string): string | null {
  if (!/^[a-z0-9_]+\.py$/.test(name)) return null;
  const dir = skillsDir();
  if (!fs.existsSync(dir)) return null;
  for (const skill of fs.readdirSync(dir)) {
    const candidate = path.join(dir, skill, "scripts", name);
    if (fs.existsSync(candidate)) {
      const real = fs.realpathSync(candidate);
      if (!real.startsWith(fs.realpathSync(dir))) return null;
      return real;
    }
  }
  return null;
}

function listAnalyzers(): string[] {
  const dir = skillsDir();
  if (!fs.existsSync(dir)) return [];
  const names: string[] = [];
  for (const skill of fs.readdirSync(dir)) {
    const scripts = path.join(dir, skill, "scripts");
    if (!fs.existsSync(scripts)) continue;
    for (const file of fs.readdirSync(scripts)) {
      if (file.endsWith(".py")) names.push(file);
    }
  }
  return Array.from(new Set(names)).sort();
}

function unsafeArg(arg: string): boolean {
  if (typeof arg !== "string" || arg.length === 0 || arg.length > 400) return true;
  return /[\u0000-\u001f;|`$]/.test(arg);
}

export default function (pi: ExtensionAPI) {
  // ── Tool: scan_secrets ──
  pi.registerTool({
    name: "scan_secrets",
    label: "Scan Secrets",
    description:
      "Scan text for exposed credentials and redact them. Detects AWS access keys, session tokens, " +
      "Authorization headers, Alibaba/Tencent/Baidu Cloud AK/SK, rclone config secrets, private keys, " +
      "and API tokens. Returns findings (type + sha256 fingerprint) and the redacted text. Input and " +
      "tool output are already redacted at the runtime boundary; use this to check a file you are about " +
      "to quote in a report, or to explain which credential class leaked.",
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
        content: [
          {
            type: "text",
            text: JSON.stringify({
              findings: scan.findings,
              count: scan.findings.length,
              redacted_text: scan.redacted,
              truncated: scan.truncated,
            }),
          },
        ],
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
      "Classify the issue domain from evidence text and report the recommended skill, the canonical " +
      "root-cause ids that skill may emit, and a best-effort storage provider (aws/bos/oss/cos/gcs/azure/obs/minio) " +
      "detected from endpoint/headers/CLI. Routing is a hint: confirm it against the evidence, and use the " +
      "probes when a configuration fact decides the answer.",
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
      const top = domains[0]?.domain || "";
      const contract = top ? DOMAINS[top] : undefined;

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              domains,
              recommended_skill: top || null,
              allowed_root_causes: contract?.ids || [],
              ambiguous: domains.length > 1 && Math.abs(domains[0].confidence - domains[1].confidence) < 0.1,
              provider: provider.provider,
              provider_confidence: provider.confidence,
              provider_signals: provider.signals,
              provider_quirks_ref: provider.quirks_ref,
              providers: provider.providers,
              provider_note:
                provider.provider === "unknown"
                  ? "Provider not identified from the evidence; probe the endpoint (probe_endpoint) or ask for a response header."
                  : "Detected provider is a hint. probe_capabilities confirms which APIs the endpoint actually implements.",
            }),
          },
        ],
        details: {
          topDomain: top || "unknown",
          recommendedSkill: top || "unknown",
          topConfidence: domains[0]?.confidence || 0,
          domainCount: domains.length,
          provider: provider.provider,
        },
      };
    },
  });

  // ── Tool: probe_endpoint ──
  pi.registerTool({
    name: "probe_endpoint",
    label: "Probe Endpoint",
    description:
      "Measure one storage endpoint without changing anything: DNS answers, TCP connect, TLS handshake " +
      "(certificate subject/issuer/expiry, protocol, ALPN), HTTP HEAD status and timing, region header, " +
      "and clock skew against the server's Date header. Use this before blaming a client for timeouts, " +
      "TLS errors, DNS failures, or SignatureDoesNotMatch caused by skew.",
    parameters: Type.Object({
      target: Type.String({ description: "Host or URL, e.g. s3.us-east-1.amazonaws.com or https://minio.internal:9000" }),
      insecure: Type.Optional(Type.Boolean({ description: "Skip certificate verification (self-signed internal endpoint)", default: false })),
      timeout_ms: Type.Optional(Type.Number({ description: "Per-step timeout in ms (default 12000, max 30000)" })),
    }),
    async execute(_toolCallId, params) {
      const result = await probeEndpoint({ target: params.target, insecure: Boolean(params.insecure), timeout_ms: params.timeout_ms });
      if (!result.ok) {
        return { content: [{ type: "text", text: JSON.stringify(result) }], isError: true, details: {} };
      }
      const evidence = registerEvidence("probe_endpoint", result.target, evidenceSummary(result.target, result.facts));
      return {
        content: [{ type: "text", text: JSON.stringify({ evidence_id: evidence.id, ...result }) }],
        details: { evidenceId: evidence.id, host: result.facts.host, warnings: result.warnings },
      };
    },
  });

  // ── Tool: probe_bucket ──
  pi.registerTool({
    name: "probe_bucket",
    label: "Probe Bucket",
    description:
      "Read a bucket's configuration, read-only, with your own credentials: versioning, encryption (SSE/KMS), " +
      "public access block, policy status and policy, CORS, lifecycle transitions, replication, event " +
      "notifications, ACL grants, ownership controls, object lock, location, and a 10-object listing. " +
      "Returns structured facts plus redacted raw XML. This is the evidence behind most 403, CORS, " +
      "lifecycle, replication, and notification diagnoses. Credentials come from the environment or " +
      "~/.aws/credentials; they are never returned.",
    parameters: Type.Object({
      bucket: Type.String({ description: "Bucket name" }),
      endpoint: Type.Optional(Type.String({ description: "Custom endpoint, e.g. https://oss-cn-hangzhou.aliyuncs.com (path-style)" })),
      region: Type.Optional(Type.String({ description: "Signing region; discovered from the endpoint when omitted" })),
      profile: Type.Optional(Type.String({ description: "AWS shared-credentials profile (default: AWS_PROFILE or 'default')" })),
      ops: Type.Optional(
        Type.Array(Type.String(), {
          description:
            "Subset of ops: head_bucket, location, versioning, encryption, public_access_block, policy_status, " +
            "policy, cors, lifecycle, replication, notification, acl, ownership, object_lock, list_objects",
        }),
      ),
      insecure: Type.Optional(Type.Boolean({ description: "Skip certificate verification", default: false })),
    }),
    async execute(_toolCallId, params) {
      const result = await probeBucket({
        bucket: params.bucket,
        endpoint: params.endpoint,
        region: params.region,
        profile: params.profile,
        ops: params.ops,
        insecure: Boolean(params.insecure),
      });
      if (!result.ok) {
        return { content: [{ type: "text", text: JSON.stringify(result) }], isError: true, details: {} };
      }
      const facts = result.facts as Record<string, unknown>;
      const evidence = registerEvidence("probe_bucket", result.bucket, evidenceSummary(result.bucket, facts));
      return {
        content: [{ type: "text", text: JSON.stringify({ evidence_id: evidence.id, ...result }) }],
        details: {
          evidenceId: evidence.id,
          bucket: result.bucket,
          region: result.region,
          failedOps: result.ops.filter(op => op.outcome !== "ok").map(op => op.op),
        },
      };
    },
  });

  // ── Tool: probe_capabilities ──
  pi.registerTool({
    name: "probe_capabilities",
    label: "Probe Capabilities",
    description:
      "Ask an endpoint what it actually implements instead of guessing from its hostname: HEAD bucket, " +
      "ListObjectsV2, location, versioning, CORS, policy, ACL, and object-lock, each classified as ok / " +
      "denied / not configured / unsupported. Use this to identify the provider and to separate " +
      "'you lack permission' from 'this endpoint does not implement the API'.",
    parameters: Type.Object({
      endpoint: Type.String({ description: "Endpoint host or URL, e.g. https://s3.bj.bcebos.com" }),
      bucket: Type.Optional(Type.String({ description: "Bucket to probe (path-style)" })),
      region: Type.Optional(Type.String({ description: "Signing region (default us-east-1)" })),
      profile: Type.Optional(Type.String({ description: "AWS shared-credentials profile" })),
      insecure: Type.Optional(Type.Boolean({ description: "Skip certificate verification", default: false })),
    }),
    async execute(_toolCallId, params) {
      const result = await probeCapabilities({
        endpoint: params.endpoint,
        bucket: params.bucket,
        region: params.region,
        profile: params.profile,
        insecure: Boolean(params.insecure),
      });
      if (!result.ok) {
        return { content: [{ type: "text", text: JSON.stringify(result) }], isError: true, details: {} };
      }
      const summary = {
        provider_guess: result.provider_guess,
        auth: result.auth,
        supported: result.ops.filter(op => op.outcome === "ok").map(op => op.op),
        denied: result.ops.filter(op => op.outcome === "denied").map(op => op.op),
        unsupported: result.ops.filter(op => op.outcome === "unsupported").map(op => op.op),
      };
      const evidence = registerEvidence("probe_capabilities", result.endpoint, evidenceSummary(result.endpoint, summary));
      return {
        content: [{ type: "text", text: JSON.stringify({ evidence_id: evidence.id, ...result }) }],
        details: { evidenceId: evidence.id, provider: result.provider_guess },
      };
    },
  });

  // ── Tool: run_analyzer ──
  pi.registerTool({
    name: "run_analyzer",
    label: "Run Analyzer",
    description:
      "Run one of StorageOps' deterministic analyzers (the Python scripts shipped in the skill packs) on " +
      "local artifacts: access logs, bucket/IAM policies, lifecycle configs, SigV4 errors, sync logs, " +
      "ETag/checksum math, migration sizing, throttling math. No shell: the script name must be in the " +
      "shipped allowlist and arguments are passed as an argv array. Pass --stdin data through 'stdin' " +
      "instead of shell pipes. Returns the analyzer's JSON.",
    parameters: Type.Object({
      analyzer: Type.String({ description: "Script file name, e.g. parse_access_log.py or policy_analyzer.py" }),
      args: Type.Optional(Type.Array(Type.String(), { description: "Arguments, one array element each" })),
      stdin: Type.Optional(Type.String({ description: "Text to write to the analyzer's stdin (replaces shell pipes)" })),
      timeout_ms: Type.Optional(Type.Number({ description: "Timeout in ms (default 30000, max 120000)" })),
    }),
    async execute(_toolCallId, params) {
      const script = analyzerPath(params.analyzer || "");
      if (!script) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                ok: false,
                error: `unknown analyzer: ${params.analyzer}`,
                available: listAnalyzers(),
              }),
            },
          ],
          isError: true,
          details: {},
        };
      }
      const args = (params.args || []).map(String);
      const bad = args.find(unsafeArg);
      if (bad !== undefined) {
        return {
          content: [{ type: "text", text: JSON.stringify({ ok: false, error: `unsafe argument: ${bad}` }) }],
          isError: true,
          details: {},
        };
      }
      if (args.length > 20) {
        return {
          content: [{ type: "text", text: JSON.stringify({ ok: false, error: "too many arguments (max 20)" }) }],
          isError: true,
          details: {},
        };
      }
      const timeout = Math.min(Math.max(Number(params.timeout_ms || 30_000), 1000), 120_000);
      const python = process.env.STORAGEOPS_PYTHON || "python3";

      const run = await new Promise<{ code: number | null; stdout: string; stderr: string }>(resolve => {
        // Analyzers are documented as `python3 scripts/<name>.py` run from the
        // skill directory, so resolve relative paths from there.
        const child = childProcess.spawn(python, [script, ...args], {
          cwd: path.dirname(path.dirname(script)),
          stdio: ["pipe", "pipe", "pipe"],
        });
        let stdout = "";
        let stderr = "";
        let settled = false;
        const finish = (code: number | null) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolve({ code, stdout, stderr });
        };
        const timer = setTimeout(() => {
          child.kill("SIGKILL");
          finish(null);
        }, timeout);
        child.stdout.on("data", chunk => {
          if (stdout.length < 200_000) stdout += chunk.toString("utf8");
        });
        child.stderr.on("data", chunk => {
          if (stderr.length < 40_000) stderr += chunk.toString("utf8");
        });
        child.on("error", error => {
          stderr += (error as Error).message;
          finish(null);
        });
        child.on("close", code => finish(code));
        if (params.stdin) child.stdin.write(params.stdin);
        child.stdin.end();
      });

      const redactedOut = redactText(run.stdout.slice(0, 20_000)).redacted;
      let parsed: unknown;
      try {
        parsed = JSON.parse(run.stdout);
      } catch {
        parsed = undefined;
      }
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              ok: run.code === 0,
              analyzer: params.analyzer,
              exit_code: run.code,
              json: parsed,
              stdout: parsed === undefined ? redactedOut : undefined,
              stderr: redactText(run.stderr.slice(0, 2000)).redacted || undefined,
              timeout_ms: timeout,
            }),
          },
        ],
        isError: run.code !== 0,
        details: { analyzer: params.analyzer, exitCode: run.code },
      };
    },
  });

  // ── Tool: capture_http_trace ──
  pi.registerTool({
    name: "capture_http_trace",
    label: "Capture HTTP Trace",
    description:
      "Run ONE bounded read-only storage command through httpmon and return a sanitized HTTP summary " +
      "(status, headers, SigV4 credential scope, S3 error code, response trailers, timing). Rejects " +
      "mutating commands, shells, presigned URL material, body capture, and replay. Write failures " +
      "(a failing PUT/copy) are diagnosed from the server error body and the client's own debug dump, " +
      "never by re-sending the write.",
    parameters: Type.Object({
      command: Type.Array(Type.String(), {
        description: "Command argv array, e.g. ['aws','s3api','head-object','--bucket','b','--key','k']",
      }),
      filter_host: Type.String({ description: "Required host filter, e.g. s3.example.com" }),
      max_requests: Type.Optional(Type.Number({ description: "Maximum captured requests, capped at 20", default: 20 })),
      max_seconds: Type.Optional(Type.Number({ description: "Maximum runtime seconds, capped at 30", default: 30 })),
      capture_body: Type.Optional(Type.Boolean({ description: "Must stay false", default: false })),
    }),
    async execute(_toolCallId, params) {
      const result = await captureHttpTrace({
        command: Array.isArray(params.command) ? params.command : [],
        filter_host: params.filter_host || "",
        max_requests: params.max_requests,
        max_seconds: params.max_seconds,
        capture_body: params.capture_body,
      });
      const traceStatus = (result as any).status;
      const summary = (result as any).requests?.length
        ? `${(result as any).requests.length} request(s): ${(result as any).requests
            .slice(0, 4)
            .map((r: any) => `${r.method} ${r.status ?? "?"}`)
            .join(", ")}`
        : String((result as any).reason || (result as any).status || "no requests captured");
      // A rejected trace is guidance, not evidence: do not mint an id for it.
      const evidence =
        traceStatus === "rejected" ? null : registerEvidence("capture_http_trace", (result as any).filter_host || "trace", summary);
      return {
        content: [{ type: "text", text: JSON.stringify({ ...(evidence ? { evidence_id: evidence.id } : {}), ...result }) }],
        details: { evidenceId: evidence?.id, status: traceStatus, requestCount: (result as any).request_count || 0 },
      };
    },
  });

  // ── Tool: search_cases ──
  pi.registerTool({
    name: "search_cases",
    label: "Search Cases",
    description:
      "Search past StorageOps diagnoses recorded by submit_diagnosis. Returns case ids, root cause, route, " +
      "confidence, and a redacted summary — one record per solved case, not a transcript grep. Use it when " +
      "the current symptom looks familiar, then verify against this environment's evidence.",
    parameters: Type.Object({
      query: Type.String({ description: "Symptom, error code, provider, or root cause" }),
      limit: Type.Optional(Type.Number({ description: "Maximum results (default 5)", default: 5 })),
    }),
    async execute(_toolCallId, params) {
      const query = params.query || "";
      if (!query.trim()) {
        return { content: [{ type: "text", text: JSON.stringify({ results: [], note: "Empty query" }) }], details: {} };
      }
      const results = searchCases(query, typeof params.limit === "number" ? params.limit : 5);
      return {
        content: [{ type: "text", text: JSON.stringify({ results, query }) }],
        details: { resultCount: results.length },
      };
    },
  });

  // ── Tool: submit_diagnosis ──
  pi.registerTool({
    name: "submit_diagnosis",
    label: "Submit Diagnosis",
    description:
      "Submit the final diagnosis. Validated at runtime: the root cause must be one of the route's contract " +
      "ids, every evidence id must come from a probe in this session, at least one falsifier is required, " +
      "and remediation must be manual-only (apply_by=human). On success it records a searchable case and " +
      "returns the canonical report: reply with that report unchanged as your final answer.",
    parameters: Type.Object({
      route: Type.String({ description: `One of: ${routes().join(", ")}` }),
      provider: Type.Optional(Type.String({ description: "aws|bos|oss|cos|obs|gcs|azure|minio|ceph|other" })),
      confidence: Type.Number({ description: "0..1; calibrate against the evidence you actually gathered" }),
      primary: Type.Object({
        root_cause_type: Type.String({ description: "Canonical id from the route's allowed_root_causes" }),
        affected_layer: Type.String({ description: "client-sdk | request-encoding | bucket-policy | iam | kms | network-path | service | cache" }),
        mechanism: Type.String({ description: "How the failure happens, in one or two sentences" }),
      }),
      alternatives: Type.Optional(
        Type.Array(
          Type.Object({
            root_cause_type: Type.String(),
            why_rejected: Type.String({ description: "The evidence that ruled it out" }),
          }),
        ),
      ),
      evidence: Type.Array(
        Type.Object({
          id: Type.String({ description: "Evidence id returned by a probe (ev_N)" }),
          claim: Type.String({ description: "What this evidence shows for the diagnosis" }),
        }),
      ),
      remediation: Type.Array(
        Type.Object({
          action: Type.String(),
          risk: Type.String({ description: "none | low | medium | high" }),
          reversible: Type.Boolean(),
          apply_by: Type.String({ description: "human (StorageOps never applies changes)" }),
        }),
      ),
      falsifiers: Type.Array(Type.String({ description: "Observations that would disprove this diagnosis" })),
      open_questions: Type.Optional(Type.Array(Type.String())),
    }),
    async execute(_toolCallId, params) {
      const validation = validateDiagnosis(params as unknown as DiagnosisInput, new Set(listEvidence().map(e => e.id)));
      if (!validation.ok) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                ok: false,
                errors: validation.errors,
                allowed_root_causes: validation.allowed_root_causes,
                evidence_ids: listEvidence().map(e => e.id),
              }),
            },
          ],
          isError: true,
          details: { errors: validation.errors },
        };
      }
      const casePath = recordCase(validation.diagnosis);
      return {
        content: [{ type: "text", text: validation.markdown }],
        details: {
          diagnosis: validation.diagnosis,
          case_path: casePath,
          contract_version: validation.diagnosis.contract_version,
        },
      };
    },
  });

  // ── Runtime guards ──
  // In the StorageOps launcher (STORAGEOPS_ENFORCE_READONLY=1) the tool set is
  // read-only by construction. These hooks keep the invariant even if a user
  // passes extra flags, and stop the agent from reading credential stores.
  pi.on("input", async (event, _ctx) => {
    if (process.env.STORAGEOPS_ENFORCE_READONLY !== "1") return;
    if (event.source === "extension") return;
    const scan = redactText(event.text || "");
    if (scan.findings.length === 0) return;
    const note =
      `\n\n[storageops] ${scan.findings.length} credential value(s) redacted before analysis ` +
      `(${[...new Set(scan.findings.map(f => f.type))].join(", ")}).`;
    return { action: "transform", text: scan.redacted + note };
  });

  pi.on("tool_call", async (event, _ctx) => {
    if (process.env.STORAGEOPS_ENFORCE_READONLY !== "1") return;
    if (WRITE_TOOLS.has(event.toolName)) {
      return {
        block: true,
        reason:
          `${event.toolName} is disabled in StorageOps diagnose mode. Use the read-only tools: probe_endpoint, ` +
          `probe_bucket, probe_capabilities, run_analyzer, capture_http_trace, read, grep, find, ls.`,
      };
    }
    if (event.toolName === "read") {
      const target = String((event.input as any)?.path || "");
      if (CREDENTIAL_PATHS.test(target)) {
        return {
          block: true,
          reason:
            "Refusing to read a credential store. StorageOps never needs raw credentials: probe tools read them " +
            "from the environment or ~/.aws/credentials internally and return only a redacted identity label.",
        };
      }
    }
    return;
  });

  pi.on("tool_result", async (event, _ctx) => {
    if (process.env.STORAGEOPS_ENFORCE_READONLY !== "1") return;
    const guarded = new Set(["read", "grep", "find", "ls", "capture_http_trace", "run_analyzer", "probe_bucket", "probe_capabilities", "probe_endpoint"]);
    if (!guarded.has(event.toolName)) return;
    const content = Array.isArray(event.content) ? event.content : [];
    let changed = false;
    const next = content.map(block => {
      if (block.type !== "text" || typeof block.text !== "string") return block;
      const scan = redactText(block.text);
      if (scan.findings.length === 0) return block;
      changed = true;
      return { ...block, text: scan.redacted };
    });
    return changed ? { content: next } : undefined;
  });

  pi.on("before_agent_start", async (event, _ctx) => {
    if (process.env.STORAGEOPS_MODE !== "diagnose") return;
    const options = (event as any).systemPromptOptions;
    if (!options) return;
    if (options.sections && !options.sections.storageops) {
      options.sections.storageops = `<storageops>\n${PERSONA}\n</storageops>`;
    }
    if (Array.isArray(options.promptGuidelines) && !options.promptGuidelines.includes("storageops-evidence-first")) {
      options.promptGuidelines.push(
        "storageops-evidence-first: gather evidence with the read-only probes before concluding, and finish with submit_diagnosis.",
      );
    }
    return;
  });

  // ── Session startup ──
  pi.on("session_start", async (_event, ctx) => {
    const dir = skillsDir();
    let packs = 0;
    if (fs.existsSync(dir)) packs = fs.readdirSync(dir).filter(name => fs.statSync(path.join(dir, name)).isDirectory()).length;
    const creds = resolveCredentials();
    ctx.logger?.log(
      `StorageOps ${CONTRACT_VERSION}: ${packs} skill packs, ${Object.keys(DOMAINS).length} domains, ` +
        `credential source ${credentialLabel(creds)}`,
    );
  });
}
