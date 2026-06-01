/**
 * StorageOps Pi Extension
 *
 * Registers all 21 StorageOps diagnostic tools so Pi's LLM can call them
 * natively during multi-turn diagnosis sessions. Each tool delegates to
 * storageops-core via a lightweight Python bridge subprocess.
 *
 * Placement: .pi/extensions/storageops.ts (auto-discovered by Pi)
 * Reload:    /reload inside Pi session
 */
import { spawnSync } from "child_process";
import * as path from "path";

// Bridge script relative to this extension file: .pi/extensions/ → repo root → cli
const BRIDGE = path.resolve(
  __dirname,
  "..",
  "..",
  "storageops-cli",
  "storageops",
  "runtime",
  "tool_bridge.py"
);

function callTool(name: string, inputs: unknown): unknown {
  const result = spawnSync("python3", [BRIDGE], {
    input: JSON.stringify({ tool: name, inputs }),
    encoding: "utf8",
    timeout: 30_000,
  });
  if (result.error) {
    return { error: `Bridge spawn error: ${result.error.message}` };
  }
  if (result.status !== 0) {
    return { error: `Bridge exited ${result.status}: ${result.stderr?.trim()}` };
  }
  try {
    return JSON.parse(result.stdout);
  } catch {
    return { error: "Bridge returned non-JSON output", raw: result.stdout?.slice(0, 500) };
  }
}

// ── Tool Definitions ─────────────────────────────────────────────────────────

interface ToolDef {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

const TOOLS: ToolDef[] = [
  {
    name: "scan_secrets",
    description:
      "Scan text for exposed credentials and redact them. Detects AWS access keys (AKIA...), " +
      "session tokens, Authorization headers, Alibaba/Tencent/Baidu Cloud AK/SK, rclone config " +
      "secrets, private keys. Returns findings list + redacted_text. " +
      "Call BEFORE passing any user-provided text to other tools or including it in your response.",
    inputSchema: {
      type: "object",
      properties: { text: { type: "string", description: "Text to scan for secrets" } },
      required: ["text"],
    },
  },
  {
    name: "parse_rclone_log",
    description:
      "Parse an rclone debug or info log. Use when evidence contains rclone output, e.g. " +
      "'ERROR ... corrupted on transfer' or 'rclone v1.64.2'. Extracts: rclone version, " +
      "transfer failures, ETag/checksum mismatches (multipart_etag_format_mismatch is most " +
      "common cause of corrupted-on-transfer), retry counts, timeouts, bandwidth stats. " +
      "Call AFTER scan_secrets.",
    inputSchema: {
      type: "object",
      properties: {
        log_text: { type: "string", description: "Raw rclone log content (already redacted)" },
      },
      required: ["log_text"],
    },
  },
  {
    name: "parse_sigv4_error",
    description:
      "Parse an AWS SigV4 error XML response. Use when evidence contains XML with " +
      "'<Code>SignatureDoesNotMatch</Code>' or '<Code>RequestExpired</Code>', " +
      "InvalidSignature, AuthorizationHeaderMalformed. Extracts error code, canonical " +
      "request diff, string-to-sign, server time (clock skew >5 min causes RequestExpired). " +
      "Call AFTER scan_secrets; provide system_time if user ran `date -u`.",
    inputSchema: {
      type: "object",
      properties: {
        xml_text: { type: "string", description: "Raw XML error response body" },
        system_time: { type: "string", description: "Client system time from `date -u` for clock skew check" },
      },
      required: ["xml_text"],
    },
  },
  {
    name: "parse_awscli_debug",
    description:
      "Parse AWS CLI debug log output. Use when evidence contains AWS CLI debug lines like " +
      "'DEBUG botocore.endpoint' or 'urllib3.connectionpool'. Also useful for s5cmd logs and " +
      "generic HTTP traces. Extracts HTTP status codes, error codes (SignatureDoesNotMatch, " +
      "AccessDenied, NoSuchKey), credential source, endpoint URL, request/response headers. " +
      "Call AFTER scan_secrets.",
    inputSchema: {
      type: "object",
      properties: {
        log_text: { type: "string", description: "Raw AWS CLI debug log content" },
      },
      required: ["log_text"],
    },
  },
  {
    name: "parse_lifecycle_xml",
    description:
      "Parse an S3 lifecycle configuration XML. Use when evidence contains XML starting with " +
      "'<LifecycleConfiguration>' or user asks about lifecycle rules, transitions, or expiration. " +
      "Extracts all rules, detects overlapping prefixes, warns about STANDARD_IA or GLACIER " +
      "transitions without ObjectSizeGreaterThan filter (objects <128KB billed at 128KB minimum — " +
      "most common lifecycle cost trap). Call BEFORE analyze_cost or generate_lifecycle_fix.",
    inputSchema: {
      type: "object",
      properties: {
        xml_text: { type: "string", description: "S3 lifecycle configuration XML text" },
      },
      required: ["xml_text"],
    },
  },
  {
    name: "analyze_policy",
    description:
      "Trace a 403 AccessDenied through IAM and/or bucket policies. Use when user reports " +
      "403 / AccessDenied errors. Handles: explicit Deny overriding Allow, cross-account access " +
      "where BOTH IAM and bucket policy must allow, missing Allow, condition mismatches " +
      "(aws:SourceVpc, aws:PrincipalOrgID), KMS key policy gaps. Supports action wildcards s3:Get*. " +
      "If policy JSON is unavailable, pass error_text for inline text analysis. " +
      "Call generate_policy_fix afterward if a fix statement is needed.",
    inputSchema: {
      type: "object",
      properties: {
        principal: { type: "string", description: "ARN of the principal attempting access" },
        action: { type: "string", description: "S3 action, e.g. s3:GetObject" },
        resource: { type: "string", description: "ARN of the resource" },
        iam_policy: { type: "object", description: "IAM policy JSON with Statement array" },
        bucket_policy: { type: "object", description: "Bucket policy JSON with Statement array" },
        error_text: { type: "string", description: "Raw 403 error text when policy JSON is unavailable" },
      },
    },
  },
  {
    name: "analyze_cost",
    description:
      "Analyze per-prefix inventory data for storage cost issues. Use when user reports " +
      "unexpectedly high bills or provides inventory with object counts, sizes, storage classes. " +
      "Detects: minimum billable size penalty (STANDARD_IA/Glacier objects <128KB billed at 128KB), " +
      "minimum storage duration charges (STANDARD_IA: 30 days, Glacier: 90-180 days), cost " +
      "amplification from many small objects in tiered storage.",
    inputSchema: {
      type: "object",
      properties: {
        storage_price_per_gb: { type: "object", description: "Price per GB per storage class (defaults used if omitted)" },
        prefixes: {
          type: "array",
          description: "Per-prefix inventory data",
          items: {
            type: "object",
            properties: {
              prefix: { type: "string" },
              storage_class: { type: "string" },
              object_count: { type: "integer" },
              total_size_bytes: { type: "integer" },
              avg_object_age_days: { type: "number" },
            },
            required: ["prefix", "storage_class", "object_count", "total_size_bytes"],
          },
        },
      },
      required: ["prefixes"],
    },
  },
  {
    name: "detect_throttling",
    description:
      "Detect S3 throttling patterns from HTTP status code and error distributions. Use when " +
      "evidence mentions 429, SlowDown, RequestRateLimitExceeded, or intermittent poor speeds " +
      "with retries. Returns: throttle_rate_percent, severity (low/medium/high/critical), " +
      "affected prefixes (hot prefix detection), retry recommendations. " +
      "Extract status_codes and errors from parse_awscli_debug or parse_rclone_log first.",
    inputSchema: {
      type: "object",
      properties: {
        status_codes: { type: "object", description: "HTTP status code counts, e.g. {\"429\": 10, \"200\": 1000}" },
        errors: { type: "array", description: "Array of error objects from the log", items: {} },
        total_operations: { type: "integer", description: "Total operations in measurement window" },
        prefix_errors: { type: "object", description: "Error counts keyed by prefix" },
      },
    },
  },
  {
    name: "generate_lifecycle_fix",
    description:
      "Generate a corrected S3 lifecycle XML fixing issues from parse_lifecycle_xml. " +
      "Call AFTER parse_lifecycle_xml confirmed problems (missing size filter, overlapping " +
      "prefixes, too-short transition delay). Adds ObjectSizeGreaterThan 128KB filter to " +
      "STANDARD_IA/Glacier transitions, enforces 30-day minimum, deduplicates overlapping rules. " +
      "Output must be reviewed and applied manually — label as '# manual-only:'.",
    inputSchema: {
      type: "object",
      properties: {
        xml_text: { type: "string", description: "Original lifecycle configuration XML to fix" },
      },
      required: ["xml_text"],
    },
  },
  {
    name: "generate_policy_fix",
    description:
      "Generate specific IAM or bucket policy statement(s) to fix a 403 AccessDenied. " +
      "Call AFTER analyze_policy identified the denial source. Outputs a ready-to-paste policy " +
      "JSON statement for the exact gap. " +
      "Output MUST be reviewed before applying — label as '# manual-only:'.",
    inputSchema: {
      type: "object",
      properties: {
        principal: { type: "string", description: "ARN of the denied principal" },
        action: { type: "string", description: "S3 action, e.g. s3:GetObject" },
        resource: { type: "string", description: "Resource ARN" },
        iam_policy: { type: "object", description: "IAM policy JSON" },
        bucket_policy: { type: "object", description: "Bucket policy JSON" },
      },
    },
  },
  {
    name: "search_memory",
    description:
      "Search past diagnosed cases by BM25 keyword similarity. " +
      "Call this as your FIRST tool (before any parsing) to check for prior art. " +
      "A match may reveal the root cause immediately. " +
      "Query with symptoms + domain keywords: 'ETag mismatch multipart rclone corrupted transfer' " +
      "or '403 AccessDenied cross-account KMS'. Always verify results against current evidence.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Keywords describing the current problem" },
        domain: { type: "string", description: "Optional domain filter, e.g. 'cli_sdk_behavior'" },
        top_k: { type: "integer", description: "Number of results to return (1-5, default 3)" },
      },
      required: ["query"],
    },
  },
  {
    name: "parse_s5cmd_log",
    description:
      "Parse s5cmd debug log output into structured operation records. Use when evidence " +
      "contains s5cmd output, e.g. lines starting with 'ERROR' or 's5cmd [0-9]'. " +
      "Extracts: operation type (cp/sync/rm), error codes, failed keys, throughput stats, " +
      "retry patterns. Call AFTER scan_secrets.",
    inputSchema: {
      type: "object",
      properties: {
        log_text: { type: "string", description: "Raw s5cmd log content (already redacted)" },
      },
      required: ["log_text"],
    },
  },
  {
    name: "parse_cors_error",
    description:
      "Parse CORS error responses and preflight failures. Use when evidence contains " +
      "'NoSuchCORSConfiguration', 'CORSForbidden', 'Access-Control-Allow-Origin missing', " +
      "or OPTIONS preflight 403. Extracts: missing CORS headers, blocked origins/methods, " +
      "bucket name. Call AFTER scan_secrets; then call analyze_cors to generate a fix.",
    inputSchema: {
      type: "object",
      properties: { log_text: { type: "string" } },
      required: ["log_text"],
    },
  },
  {
    name: "analyze_cors",
    description:
      "Generate a CORS configuration XML that fixes detected issues. " +
      "Call AFTER parse_cors_error. Outputs ready-to-apply S3 CORS config XML. " +
      "Must be reviewed and applied manually — label as '# manual-only:'.",
    inputSchema: {
      type: "object",
      properties: {
        cors_data: { type: "object", description: "Output from parse_cors_error" },
      },
    },
  },
  {
    name: "parse_replication_status",
    description:
      "Parse CRR/SRR replication status data. Use when evidence shows " +
      "ReplicationStatus: FAILED/PENDING or replication lag. " +
      "Extracts: per-object status, rule failures, failure rate.",
    inputSchema: {
      type: "object",
      properties: { log_text: { type: "string" } },
      required: ["log_text"],
    },
  },
  {
    name: "analyze_replication",
    description:
      "Diagnose why replication is failing. Call AFTER parse_replication_status. " +
      "Returns likely cause (IAM/KMS/destination) and verification commands.",
    inputSchema: {
      type: "object",
      properties: {
        replication_data: { type: "object", description: "Output from parse_replication_status" },
      },
    },
  },
  {
    name: "parse_hadoop_s3a",
    description:
      "Parse Hadoop/Spark/Hive S3A filesystem errors. Use when evidence contains " +
      "'S3AFileSystem', 's3a://', staging/magic committer errors, or HADOOP- references. " +
      "Extracts: committer type, rename failures, credential issues.",
    inputSchema: {
      type: "object",
      properties: { log_text: { type: "string" } },
      required: ["log_text"],
    },
  },
  {
    name: "analyze_throughput",
    description:
      "Analyze upload/download throughput against theoretical limits given RTT and bandwidth. " +
      "Key insight: throughput = TCP_window / RTT; 192ms RTT with 64KB TCP window limits " +
      "single-stream to ~2.7 Mbps regardless of bandwidth. Returns: theoretical max throughput, " +
      "actual vs expected ratio, bottleneck type (bandwidth/latency/concurrency-bound), " +
      "multipart part size recommendation, suggested concurrency.",
    inputSchema: {
      type: "object",
      properties: {
        object_size_mb: { type: "number", description: "Object size in MB" },
        rtt_ms: { type: "number", description: "Round-trip time to endpoint in ms" },
        bandwidth_mbps: { type: "number", description: "Available bandwidth in Mbps" },
        observed_throughput_mbps: { type: "number", description: "Actual observed throughput in Mbps" },
        concurrency: { type: "integer", description: "Number of parallel streams" },
        part_size_mb: { type: "number", description: "Multipart upload part size in MB" },
      },
    },
  },
  {
    name: "parse_network_diagnostics",
    description:
      "Parse network diagnostic output (dig, curl -v, ping, mtr, traceroute) into a structured " +
      "dict. Use when evidence contains DNS lookup results, curl verbose output, ping stats, or " +
      "traceroute/mtr hop data for an S3 or VPC endpoint. Extracts: DNS status (NXDOMAIN/SERVFAIL/" +
      "resolved IPs/CNAME chain), TCP connectivity (refused/timed out/HTTP status), TLS cert errors, " +
      "ICMP latency and packet loss, routing hops. Follow with analyze_network.",
    inputSchema: {
      type: "object",
      properties: {
        diagnostic_text: { type: "string", description: "Raw output from dig, curl -v, ping, mtr, or traceroute" },
      },
      required: ["diagnostic_text"],
    },
  },
  {
    name: "analyze_network",
    description:
      "Root-cause network failures from parse_network_diagnostics output. Diagnoses: DNS NXDOMAIN " +
      "(bad hostname/missing VPC endpoint DNS), DNS SERVFAIL, TLS cert errors, TCP refused " +
      "(firewall/security group), TCP timeout (silent drop/NACL), packet loss, HTTP 403 (S3 policy). " +
      "Returns: root_cause, severity (critical/high/medium/low/ok), confidence score, " +
      "findings, prioritized recommendations.",
    inputSchema: {
      type: "object",
      properties: {
        parsed: { type: "object", description: "Full output dict from parse_network_diagnostics" },
      },
      required: ["parsed"],
    },
  },
  {
    name: "parse_httpmon_log",
    description:
      "Parse httpmon (https-traffic-inspector) output into StorageOps diagnostic signals. " +
      "Handles NDJSON (from `httpmon --format json`) and HAR (from `httpmon --har output.har`). " +
      "Extracts S3 signals: error codes (AccessDenied, SignatureDoesNotMatch, SlowDown), " +
      "HTTP status distribution, auth type (sigv4/presigned/anonymous), CORS headers, timing. " +
      "Auth values are never exposed — only classified.",
    inputSchema: {
      type: "object",
      properties: {
        log_text: { type: "string", description: "Raw httpmon NDJSON output or HAR file content" },
      },
      required: ["log_text"],
    },
  },
];

// ── Extension Entry Point ────────────────────────────────────────────────────

export default function (pi: {
  registerTool(tool: {
    name: string;
    description: string;
    inputSchema: Record<string, unknown>;
    execute: (args: Record<string, unknown>) => Promise<unknown>;
  }): void;
}): void {
  for (const tool of TOOLS) {
    const { name, description, inputSchema } = tool;
    pi.registerTool({
      name,
      description,
      inputSchema,
      execute: async (args) => callTool(name, args),
    });
  }
}
