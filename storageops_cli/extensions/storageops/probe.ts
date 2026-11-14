/**
 * Read-only probes: endpoint reachability, bucket configuration, and capability
 * discovery.
 *
 * Everything here is GET/HEAD against the user's endpoint. No probe mutates
 * bucket state, and no probe returns credential material — the raw XML is
 * redacted and truncated before it can reach the model.
 */

import * as dns from "dns";
import * as net from "net";
import * as tls from "tls";
import * as http from "http";
import * as https from "https";

import { credentialLabel, resolveCredentials, signRequest, type Credentials } from "./sigv4.ts";
import { redactText } from "./secrets.ts";

export type Outcome = "ok" | "denied" | "not_configured" | "unsupported" | "error";

export type ProbeFailure = {
  ok: false;
  error: string;
  warnings?: string[];
};

export type EndpointResult = {
  ok: true;
  target: string;
  facts: {
    host: string;
    port: number;
    scheme: string;
    dns: { addresses: string[]; ms: number; error?: string };
    tcp: { connected: boolean; ms: number; error?: string };
    tls?: {
      authorized: boolean;
      authorization_error?: string;
      protocol?: string;
      cipher?: string;
      alpn?: string;
      subject?: string;
      issuer?: string;
      valid_from?: string;
      valid_to?: string;
      days_remaining?: number;
      sans?: string[];
    };
    http?: {
      status?: number;
      server?: string;
      region?: string;
      request_id?: string;
      date?: string;
      skew_seconds?: number;
      ms?: number;
      error?: string;
    };
    endpoint_style: string;
    provider_hint: string;
  };
  warnings: string[];
};

export type BucketOp = {
  op: string;
  status?: number;
  outcome: Outcome;
  code?: string;
  message?: string;
};

export type BucketResult = {
  ok: true;
  bucket: string;
  endpoint: string;
  region: string;
  addressing: "virtual-hosted" | "path-style";
  credential: string;
  ops: BucketOp[];
  facts: Record<string, unknown>;
  raw: Record<string, string>;
  warnings: string[];
};

export type CapabilitiesResult = {
  ok: true;
  endpoint: string;
  bucket?: string;
  provider_guess: string;
  auth: string;
  server?: string;
  region?: string;
  ops: BucketOp[];
  notes: string[];
  warnings: string[];
};

const MAX_RAW_CHARS = 6000;
const DEFAULT_TIMEOUT_MS = 12_000;

function nowMs(): number {
  return Number(process.hrtime.bigint() / 1000000n);
}

function redactRaw(value: string): string {
  return redactText(value).redacted.slice(0, MAX_RAW_CHARS);
}

function timeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
    promise.then(
      value => {
        clearTimeout(timer);
        resolve(value);
      },
      error => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

export function parseTarget(target: string): URL | null {
  const raw = (target || "").trim();
  if (!raw) return null;
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    const url = new URL(withScheme);
    if (!url.hostname) return null;
    return url;
  } catch {
    return null;
  }
}

function defaultPort(url: URL): number {
  return url.port ? Number(url.port) : url.protocol === "http:" ? 80 : 443;
}

async function resolveDns(host: string): Promise<{ addresses: string[]; ms: number; error?: string }> {
  const started = nowMs();
  try {
    const records = await dns.promises.lookup(host, { all: true, verbatim: true });
    return { addresses: Array.from(new Set(records.map(r => r.address))), ms: nowMs() - started };
  } catch (error) {
    return { addresses: [], ms: nowMs() - started, error: (error as Error).message };
  }
}

async function tcpConnect(host: string, port: number, timeoutMs: number): Promise<{ connected: boolean; ms: number; error?: string }> {
  const started = nowMs();
  return new Promise(resolve => {
    const socket = net.connect({ host, port });
    let settled = false;
    const done = (connected: boolean, error?: string) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve({ connected, ms: nowMs() - started, error });
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false, `tcp connect timed out after ${timeoutMs}ms`));
    socket.once("error", error => done(false, error.message));
  });
}

async function tlsHandshake(host: string, port: number, timeoutMs: number): Promise<EndpointResult["facts"]["tls"]> {
  return new Promise(resolve => {
    const socket = tls.connect({
      host,
      port,
      servername: host,
      ALPNProtocols: ["h2", "http/1.1"],
      rejectUnauthorized: false,
    });
    let settled = false;
    const done = (value: EndpointResult["facts"]["tls"]) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(value);
    };
    socket.setTimeout(timeoutMs);
    socket.once("secureConnect", () => {
      const cert = socket.getPeerCertificate() as tls.DetailedPeerCertificate & { validTo?: string; validFrom?: string };
      const cipher = socket.getCipher();
      let daysRemaining: number | undefined;
      const expiry = cert.validTo || cert.valid_to;
      if (expiry) {
        const expires = Date.parse(expiry);
        if (!Number.isNaN(expires)) daysRemaining = Math.round((expires - Date.now()) / 86_400_000);
      }
      done({
        authorized: socket.authorized,
        authorization_error: socket.authorized ? undefined : String(socket.authorizationError || ""),
        protocol: socket.getProtocol() || undefined,
        cipher: cipher?.name,
        alpn: socket.alpnProtocol || undefined,
        subject: cert.subject?.CN,
        issuer: cert.issuer?.CN,
        valid_from: cert.validFrom || cert.valid_from,
        valid_to: cert.validTo || cert.valid_to,
        days_remaining: daysRemaining,
        sans: cert.subjectaltname
          ? cert.subjectaltname.split(",").map(part => part.trim().replace(/^DNS:/, "")).slice(0, 20)
          : undefined,
      });
    });
    socket.once("timeout", () => done({ authorized: false, authorization_error: `tls handshake timed out after ${timeoutMs}ms` }));
    socket.once("error", error => done({ authorized: false, authorization_error: error.message }));
  });
}

export type HttpResponse = {
  status: number;
  headers: http.IncomingHttpHeaders;
  body: string;
  ms: number;
};

export function request(
  url: URL,
  options: { method?: string; headers?: Record<string, string>; timeoutMs?: number; insecure?: boolean } = {},
): Promise<HttpResponse> {
  const timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
  const transport = url.protocol === "http:" ? http : https;
  const started = nowMs();
  return new Promise((resolve, reject) => {
    const req = transport.request(
      {
        method: options.method || "GET",
        protocol: url.protocol,
        hostname: url.hostname,
        port: url.port || undefined,
        path: `${url.pathname}${url.search}`,
        headers: { "user-agent": "storageops/2.0", accept: "*/*", ...(options.headers || {}) },
        rejectUnauthorized: options.insecure ? false : true,
        timeout: timeoutMs,
      },
      res => {
        const chunks: Buffer[] = [];
        let size = 0;
        res.on("data", chunk => {
          if (size < 131_072) chunks.push(chunk as Buffer);
          size += (chunk as Buffer).length;
        });
        res.on("end", () =>
          resolve({
            status: res.statusCode || 0,
            headers: res.headers,
            body: Buffer.concat(chunks).toString("utf8"),
            ms: nowMs() - started,
          }),
        );
      },
    );
    req.on("timeout", () => req.destroy(new Error(`request timed out after ${timeoutMs}ms`)));
    req.on("error", reject);
    req.end();
  });
}

function headerValue(headers: http.IncomingHttpHeaders, name: string): string | undefined {
  const value = headers[name.toLowerCase()];
  if (Array.isArray(value)) return value[0];
  return value;
}

function providerFromServerHeader(server?: string): string {
  const value = (server || "").toLowerCase();
  if (!value) return "unknown";
  if (value.includes("amazons3")) return "aws";
  if (value.includes("minio")) return "minio";
  if (value.includes("aliyun")) return "oss";
  if (value.includes("cos")) return "cos";
  if (value.includes("bce") || value.includes("baidu")) return "bos";
  if (value.includes("obs")) return "obs";
  if (value.includes("ceph")) return "ceph";
  return "unknown";
}

function endpointStyle(host: string): string {
  if (/(^|\.)s3([.-][a-z0-9-]+)?\.amazonaws\.com$/i.test(host)) return "virtual-hosted-or-path (s3 endpoint)";
  if (/\.s3[.-]/i.test(host)) return "virtual-hosted (bucket in host)";
  if (/^(s3|oss|cos|obs)[.-]/i.test(host)) return "path-style (service host)";
  return "custom endpoint (verify addressing style)";
}

export async function probeEndpoint(input: { target: string; insecure?: boolean; timeout_ms?: number }): Promise<EndpointResult | ProbeFailure> {
  const url = parseTarget(input.target);
  if (!url) return { ok: false, error: "target must be a host or URL, e.g. s3.us-east-1.amazonaws.com" };
  const timeoutMs = Math.min(Math.max(Number(input.timeout_ms || DEFAULT_TIMEOUT_MS), 1000), 30_000);
  const host = url.hostname;
  const port = defaultPort(url);
  const warnings: string[] = [];

  const dnsResult = await resolveDns(host);
  if (dnsResult.error) warnings.push(`dns: ${dnsResult.error}`);

  const tcp = dnsResult.addresses.length ? await tcpConnect(host, port, timeoutMs) : { connected: false, ms: 0, error: "skipped (no DNS answer)" };
  if (tcp.error && dnsResult.addresses.length) warnings.push(`tcp: ${tcp.error}`);

  const tlsResult = url.protocol === "https:" && tcp.connected ? await tlsHandshake(host, port, timeoutMs) : undefined;
  if (tlsResult && !tlsResult.authorized) warnings.push(`tls: not verified (${tlsResult.authorization_error || "unknown"})`);
  if (tlsResult?.days_remaining !== undefined && tlsResult.days_remaining < 30) {
    warnings.push(`tls certificate expires in ${tlsResult.days_remaining} days`);
  }

  let httpResult: EndpointResult["facts"]["http"];
  if (tcp.connected) {
    try {
      const response = await request(url, { method: "HEAD", timeoutMs, insecure: Boolean(input.insecure) });
      const date = headerValue(response.headers, "date");
      let skew: number | undefined;
      if (date) {
        const serverTime = Date.parse(date);
        if (!Number.isNaN(serverTime)) skew = Math.round((serverTime - Date.now()) / 1000);
      }
      httpResult = {
        status: response.status,
        server: headerValue(response.headers, "server"),
        region: headerValue(response.headers, "x-amz-bucket-region"),
        request_id: headerValue(response.headers, "x-amz-request-id") || headerValue(response.headers, "x-oss-request-id"),
        date,
        skew_seconds: skew,
        ms: response.ms,
      };
      if (skew !== undefined && Math.abs(skew) > 300) {
        warnings.push(`clock skew ${skew}s vs endpoint (signature failures above ~900s)`);
      }
    } catch (error) {
      httpResult = { error: (error as Error).message };
      warnings.push(`http: ${(error as Error).message}`);
    }
  }

  return {
    ok: true,
    target: url.toString(),
    facts: {
      host,
      port,
      scheme: url.protocol.replace(":", ""),
      dns: dnsResult,
      tcp,
      tls: tlsResult,
      http: httpResult,
      endpoint_style: endpointStyle(host),
      provider_hint: providerFromServerHeader(httpResult?.server),
    },
    warnings,
  };
}

// ── Bucket configuration ────────────────────────────────────────────────────

type OpSpec = { method: "GET" | "HEAD"; query: string; label: string };

const BUCKET_OPS: OpSpec[] = [
  { method: "HEAD", query: "", label: "head_bucket" },
  { method: "GET", query: "location", label: "location" },
  { method: "GET", query: "versioning", label: "versioning" },
  { method: "GET", query: "encryption", label: "encryption" },
  { method: "GET", query: "publicAccessBlock", label: "public_access_block" },
  { method: "GET", query: "policyStatus", label: "policy_status" },
  { method: "GET", query: "policy", label: "policy" },
  { method: "GET", query: "cors", label: "cors" },
  { method: "GET", query: "lifecycle", label: "lifecycle" },
  { method: "GET", query: "replication", label: "replication" },
  { method: "GET", query: "notification", label: "notification" },
  { method: "GET", query: "acl", label: "acl" },
  { method: "GET", query: "ownershipControls", label: "ownership" },
  { method: "GET", query: "object-lock", label: "object_lock" },
  { method: "GET", query: "list-type=2&max-keys=10", label: "list_objects" },
];

const UNSAFE_OP = /(put|delete|create|copy|restore|abort|complete|upload|tag|acl-put)/i;

export function bucketUrl(bucket: string, endpoint: string | undefined, region: string): URL {
  if (endpoint) {
    const base = parseTarget(endpoint);
    if (!base) throw new Error(`invalid endpoint: ${endpoint}`);
    const url = new URL(base.toString());
    url.pathname = `/${bucket}`;
    return url;
  }
  return new URL(`https://${bucket}.s3.${region}.amazonaws.com/`);
}

function errorCode(body: string): string | undefined {
  return /<Code>([^<]{1,80})<\/Code>/i.exec(body)?.[1];
}

function errorMessage(body: string): string | undefined {
  return /<Message>([^<]{1,300})<\/Message>/i.exec(body)?.[1];
}

function outcomeFor(status: number, body: string, op: string): Outcome {
  if (status >= 200 && status < 300) return "ok";
  const code = (errorCode(body) || "").toLowerCase();
  if (status === 403) return "denied";
  if (status === 404) {
    // Sub-resources report "not configured" as 404; the bucket itself reports NoSuchBucket.
    if (/nosuchbucket/.test(code)) return "error";
    return "not_configured";
  }
  if (status === 501 || /notimplemented|notimplemented|unsupported/.test(code)) return "unsupported";
  if (status === 400 && /invalidrequest|invalidargument/.test(code) && op !== "head_bucket") return "unsupported";
  return "error";
}

function xmlBoolean(body: string, tag: string): boolean | undefined {
  const match = new RegExp(`<${tag}>\\s*([^<]+?)\\s*</${tag}>`, "i").exec(body);
  if (!match) return undefined;
  return match[1].toLowerCase() === "true";
}

function xmlText(body: string, tag: string): string | undefined {
  return new RegExp(`<${tag}>\\s*([^<]*?)\\s*</${tag}>`, "i").exec(body)?.[1];
}

function countTags(body: string, tag: string): number {
  return (body.match(new RegExp(`<${tag}[ >]`, "gi")) || []).length;
}

function allText(body: string, tag: string): string[] {
  const values: string[] = [];
  const pattern = new RegExp(`<${tag}>\\s*([^<]*?)\\s*</${tag}>`, "gi");
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(body))) values.push(match[1]);
  return values;
}

export function deriveFacts(raw: Record<string, string>): Record<string, unknown> {
  const facts: Record<string, unknown> = {};

  if (raw.versioning) {
    facts.versioning = xmlText(raw.versioning, "Status") || "never-enabled";
  }
  if (raw.encryption) {
    facts.encryption = {
      algorithm: xmlText(raw.encryption, "SSEAlgorithm"),
      kms_key_configured: Boolean(xmlText(raw.encryption, "KMSMasterKeyID")),
      bucket_key_enabled: xmlBoolean(raw.encryption, "BucketKeyEnabled"),
    };
  }
  if (raw.public_access_block) {
    facts.public_access_block = {
      block_public_acls: xmlBoolean(raw.public_access_block, "BlockPublicAcls"),
      ignore_public_acls: xmlBoolean(raw.public_access_block, "IgnorePublicAcls"),
      block_public_policy: xmlBoolean(raw.public_access_block, "BlockPublicPolicy"),
      restrict_public_buckets: xmlBoolean(raw.public_access_block, "RestrictPublicBuckets"),
    };
  }
  if (raw.policy_status) facts.policy_status = { is_public: xmlBoolean(raw.policy_status, "IsPublic") };
  facts.policy_present = Boolean(raw.policy && raw.policy.trim());
  if (raw.cors) {
    facts.cors = {
      rule_count: countTags(raw.cors, "CORSRule"),
      allowed_methods: Array.from(new Set(allText(raw.cors, "AllowedMethod"))),
      allowed_origins: allText(raw.cors, "AllowedOrigin").slice(0, 10),
      expose_headers: allText(raw.cors, "ExposeHeader").slice(0, 10),
    };
  }
  if (raw.lifecycle) {
    const transitions: Array<Record<string, unknown>> = [];
    const ruleBlocks = raw.lifecycle.split(/<Rule[ >]/i).slice(1);
    for (const block of ruleBlocks) {
      const days = xmlText(block, "Days");
      const storageClass = xmlText(block, "StorageClass");
      if (storageClass) transitions.push({ days: days ? Number(days) : undefined, storage_class: storageClass });
    }
    facts.lifecycle = {
      rule_count: countTags(raw.lifecycle, "Rule"),
      transitions,
      expiration_days: allText(raw.lifecycle, "Days").slice(0, 10).map(Number),
      abort_incomplete_days: allText(raw.lifecycle, "DaysAfterInitiation").map(Number),
    };
  }
  if (raw.replication) {
    facts.replication = {
      configured: true,
      role: xmlText(raw.replication, "Role"),
      rule_count: countTags(raw.replication, "Rule"),
      statuses: allText(raw.replication, "Status"),
      destination_buckets: allText(raw.replication, "Bucket"),
    };
  }
  if (raw.notification) {
    facts.notification = {
      topic_configurations: countTags(raw.notification, "TopicConfiguration"),
      queue_configurations: countTags(raw.notification, "QueueConfiguration"),
      lambda_configurations: countTags(raw.notification, "CloudFunctionConfiguration"),
      event_types: allText(raw.notification, "Event").slice(0, 20),
    };
  }
  if (raw.acl) {
    const uris = allText(raw.acl, "URI");
    facts.acl = {
      grant_count: countTags(raw.acl, "Grant"),
      public_grants: uris.filter(uri => /AllUsers|AuthenticatedUsers/i.test(uri)),
      owner: xmlText(raw.acl, "ID")?.slice(0, 12),
    };
  }
  if (raw.ownership) facts.ownership = xmlText(raw.ownership, "ObjectOwnership");
  if (raw.object_lock) facts.object_lock_enabled = xmlBoolean(raw.object_lock, "ObjectLockEnabled");
  if (raw.location) {
    const location = xmlText(raw.location, "LocationConstraint");
    facts.location_constraint = location || "us-east-1";
  }
  return facts;
}

export async function probeBucket(input: {
  bucket: string;
  endpoint?: string;
  region?: string;
  profile?: string;
  ops?: string[];
  insecure?: boolean;
  timeout_ms?: number;
}): Promise<BucketResult | ProbeFailure> {
  const bucket = (input.bucket || "").trim();
  if (!/^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$/.test(bucket)) {
    return { ok: false, error: "bucket must be a valid S3 bucket name" };
  }
  const requested = (input.ops || []).filter(op => {
    if (UNSAFE_OP.test(op)) return false;
    return BUCKET_OPS.some(spec => spec.label === op);
  });
  const specs = requested.length ? BUCKET_OPS.filter(spec => requested.includes(spec.label)) : BUCKET_OPS;

  const credentials: Credentials | null = resolveCredentials(input.profile);
  let region = (input.region || "").trim();
  let url: URL;
  try {
    url = bucketUrl(bucket, input.endpoint, region || "us-east-1");
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
  const addressing: BucketResult["addressing"] = input.endpoint ? "path-style" : "virtual-hosted";
  const timeoutMs = Math.min(Math.max(Number(input.timeout_ms || DEFAULT_TIMEOUT_MS), 1000), 30_000);
  const warnings: string[] = [];
  if (!credentials) warnings.push("no credentials found (env or ~/.aws/credentials); signed-only calls will be denied");

  const call = async (spec: OpSpec, target: URL, signingRegion: string) => {
    const requestUrl = new URL(target.toString());
    requestUrl.search = spec.query ? `?${spec.query}` : "";
    let headers: Record<string, string> = {};
    if (credentials) {
      headers = signRequest({
        method: spec.method,
        url: requestUrl,
        region: signingRegion || "us-east-1",
        credentials,
      }).headers;
    }
    const response = await request(requestUrl, {
      method: spec.method,
      headers,
      timeoutMs,
      insecure: Boolean(input.insecure),
    });
    return { requestUrl, response };
  };

  const ops: BucketOp[] = [];
  const raw: Record<string, string> = {};
  let headResponse: HttpResponse | undefined;

  // Discover the region from the bucket's own response before signing the rest.
  if (!region) {
    try {
      const probe = await call(specs[0], url, "us-east-1");
      headResponse = probe.response;
      const discovered = headerValue(probe.response.headers, "x-amz-bucket-region");
      if (discovered) {
        region = discovered;
      } else if (probe.response.status === 301 || probe.response.status === 400) {
        const bodyRegion = xmlText(probe.response.body, "Region") || xmlText(probe.response.body, "Endpoint");
        if (bodyRegion) region = bodyRegion.replace(/^.*?s3[.-]/, "").replace(/\.amazonaws\.com.*$/, "");
      }
    } catch (error) {
      warnings.push(`region discovery failed: ${(error as Error).message}`);
    }
    if (region) {
      try {
        url = bucketUrl(bucket, input.endpoint, region);
      } catch {
        // Keep the original URL; the discovered region is still used for signing.
      }
    }
  }

  for (const spec of specs) {
    if (headResponse && spec.label === "head_bucket" && region) {
      // The discovery call already ran; record it instead of repeating.
      const status = headResponse.status;
      const body = headResponse.body;
      ops.push({
        op: spec.label,
        status,
        outcome: outcomeFor(status, body, spec.label),
        code: errorCode(body),
        message: errorMessage(body),
      });
      if (body) raw[spec.label] = redactRaw(body);
      continue;
    }
    try {
      const { response } = await call(spec, url, region || "us-east-1");
      const outcome = outcomeFor(response.status, response.body, spec.label);
      ops.push({
        op: spec.label,
        status: response.status,
        outcome,
        code: errorCode(response.body),
        message: errorMessage(response.body),
      });
      if (response.body && outcome !== "denied") raw[spec.label] = redactRaw(response.body);
    } catch (error) {
      ops.push({ op: spec.label, outcome: "error", message: (error as Error).message });
      warnings.push(`${spec.label}: ${(error as Error).message}`);
    }
  }

  const facts = deriveFacts(raw);
  facts.bucket = bucket;
  facts.region = region || "us-east-1 (assumed)";

  return {
    ok: true,
    bucket,
    endpoint: url.toString().replace(/\?.*$/, ""),
    region: region || "us-east-1",
    addressing,
    credential: credentialLabel(credentials),
    ops,
    facts,
    raw,
    warnings,
  };
}

// ── Capability discovery ────────────────────────────────────────────────────

const CAPABILITY_OPS: OpSpec[] = [
  { method: "HEAD", query: "", label: "head_bucket" },
  { method: "GET", query: "list-type=2&max-keys=1", label: "list_objects_v2" },
  { method: "GET", query: "location", label: "get_location" },
  { method: "GET", query: "versioning", label: "get_versioning" },
  { method: "GET", query: "cors", label: "get_cors" },
  { method: "GET", query: "policy", label: "get_policy" },
  { method: "GET", query: "acl", label: "get_acl" },
  { method: "GET", query: "object-lock", label: "get_object_lock" },
];

export async function probeCapabilities(input: {
  endpoint: string;
  bucket?: string;
  region?: string;
  profile?: string;
  insecure?: boolean;
  timeout_ms?: number;
}): Promise<CapabilitiesResult | ProbeFailure> {
  const base = parseTarget(input.endpoint);
  if (!base) return { ok: false, error: "endpoint must be a host or URL" };
  const credentials: Credentials | null = resolveCredentials(input.profile);
  const region = (input.region || "us-east-1").trim();
  const timeoutMs = Math.min(Math.max(Number(input.timeout_ms || DEFAULT_TIMEOUT_MS), 1000), 30_000);
  const ops: BucketOp[] = [];
  const notes: string[] = [];
  const warnings: string[] = [];

  let server: string | undefined;
  let discoveredRegion: string | undefined;
  let auth = "unknown";

  for (const spec of CAPABILITY_OPS) {
    const url = new URL(base.toString());
    if (input.bucket) url.pathname = `/${input.bucket}`;
    url.pathname = url.pathname.replace(/\/$/, "") || "/";
    url.search = spec.query ? `?${spec.query}` : "";
    let headers: Record<string, string> = {};
    if (credentials) headers = signRequest({ method: spec.method, url, region, credentials }).headers;
    try {
      const response = await request(url, { method: spec.method, headers, timeoutMs, insecure: Boolean(input.insecure) });
      server = server || headerValue(response.headers, "server");
      discoveredRegion = discoveredRegion || headerValue(response.headers, "x-amz-bucket-region");
      const outcome = outcomeFor(response.status, response.body, spec.label);
      ops.push({ op: spec.label, status: response.status, outcome, code: errorCode(response.body), message: errorMessage(response.body) });
      if (spec.label === "head_bucket" && !credentials) {
        auth = response.status === 403 ? "credentials-required" : response.status === 404 ? "endpoint-reachable (bucket missing)" : "anonymous-ok";
      }
      if (spec.label === "list_objects_v2" && /notimplemented|notsupported/i.test(errorCode(response.body) || "")) {
        notes.push("ListObjectsV2 is not implemented; the endpoint may be S3-compatible but incomplete or a non-S3 service");
      }
    } catch (error) {
      ops.push({ op: spec.label, outcome: "error", message: (error as Error).message });
      warnings.push(`${spec.label}: ${(error as Error).message}`);
    }
  }

  const applied = new Set(ops.filter(op => op.outcome === "ok").map(op => op.op));
  const denied = new Set(ops.filter(op => op.outcome === "denied").map(op => op.op));
  if (applied.size === 0 && denied.size === 0) notes.push("no operation returned 2xx or 403; endpoint may be unreachable, proxied, or not S3");

  return {
    ok: true,
    endpoint: base.toString(),
    bucket: input.bucket,
    provider_guess: providerFromServerHeader(server),
    auth,
    server,
    region: discoveredRegion || region,
    ops,
    notes,
    warnings,
  };
}
