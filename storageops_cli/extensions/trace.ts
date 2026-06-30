import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import * as childProcess from "child_process";
import { redactText } from "./secrets.ts";

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

export async function captureHttpTrace(params: {
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
