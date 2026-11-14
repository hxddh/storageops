/**
 * SigV4 signing for read-only probes.
 *
 * StorageOps must be able to call the S3 control plane without a shell and
 * without asking the user to paste credentials into the conversation. This
 * module signs GET/HEAD requests from environment credentials or the standard
 * AWS shared credentials file; it never prints or returns secret material.
 */

import * as crypto from "crypto";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

export type Credentials = {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken?: string;
  source: "env" | "aws-file";
};

export type SignOptions = {
  method: string;
  url: URL;
  region: string;
  service?: string;
  headers?: Record<string, string>;
  payloadHash?: string;
  credentials: Credentials;
  date?: Date;
};

export type SignedHeaders = {
  headers: Record<string, string>;
  canonicalRequest: string;
  stringToSign: string;
  signature: string;
  credentialScope: string;
};

const EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

function sha256Hex(value: string | Buffer): string {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function hmac(key: Buffer | string, value: string): Buffer {
  return crypto.createHmac("sha256", key).update(value, "utf8").digest();
}

/** RFC 3986 encoding; URLSearchParams would encode a space as "+". */
export function uriEncode(value: string): string {
  return encodeURIComponent(value).replace(/[!'()*]/g, ch => `%${ch.charCodeAt(0).toString(16).toUpperCase()}`);
}

function canonicalPath(url: URL): string {
  if (!url.pathname || url.pathname === "/") return "/";
  return url.pathname
    .split("/")
    .map(segment => (segment ? uriEncode(decodeURIComponent(segment)) : segment))
    .join("/");
}

function canonicalQuery(url: URL): string {
  const pairs: Array<[string, string]> = [];
  url.searchParams.forEach((value, key) => pairs.push([key, value]));
  return pairs
    .map(([key, value]) => [uriEncode(key), uriEncode(value)] as [string, string])
    .sort((a, b) => (a[0] === b[0] ? (a[1] < b[1] ? -1 : 1) : a[0] < b[0] ? -1 : 1))
    .map(([key, value]) => `${key}=${value}`)
    .join("&");
}

function amzDate(date: Date): { full: string; short: string } {
  const iso = date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  return { full: iso, short: iso.slice(0, 8) };
}

export function signRequest(options: SignOptions): SignedHeaders {
  const service = options.service || "s3";
  const payloadHash = options.payloadHash || EMPTY_SHA256;
  const { full, short } = amzDate(options.date || new Date());
  const host = options.url.host;

  const headers: Record<string, string> = {};
  for (const [key, value] of Object.entries(options.headers || {})) {
    headers[key.toLowerCase()] = String(value).trim();
  }
  headers["host"] = host;
  headers["x-amz-date"] = full;
  headers["x-amz-content-sha256"] = payloadHash;
  if (options.credentials.sessionToken) headers["x-amz-security-token"] = options.credentials.sessionToken;

  const names = Object.keys(headers).sort();
  const canonicalHeaders = names.map(name => `${name}:${headers[name]}\n`).join("");
  const signedHeaders = names.join(";");
  const canonicalRequest = [
    options.method.toUpperCase(),
    canonicalPath(options.url),
    canonicalQuery(options.url),
    canonicalHeaders,
    signedHeaders,
    payloadHash,
  ].join("\n");

  const credentialScope = `${short}/${options.region}/${service}/aws4_request`;
  const stringToSign = ["AWS4-HMAC-SHA256", full, credentialScope, sha256Hex(canonicalRequest)].join("\n");

  const kDate = hmac(`AWS4${options.credentials.secretAccessKey}`, short);
  const kRegion = hmac(kDate, options.region);
  const kService = hmac(kRegion, service);
  const kSigning = hmac(kService, "aws4_request");
  const signature = crypto.createHmac("sha256", kSigning).update(stringToSign, "utf8").digest("hex");

  const authorization =
    `AWS4-HMAC-SHA256 Credential=${options.credentials.accessKeyId}/${credentialScope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;

  return {
    headers: { ...headers, authorization },
    canonicalRequest,
    stringToSign,
    signature,
    credentialScope,
  };
}

/** Parse one profile out of an INI-style AWS credentials/config file. */
export function parseIniProfile(text: string, profile: string): Record<string, string> {
  const wanted = [`[${profile}]`, `[profile ${profile}]`].map(s => s.toLowerCase());
  const result: Record<string, string> = {};
  let inSection = false;
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || line.startsWith(";")) continue;
    if (line.startsWith("[")) {
      inSection = wanted.includes(line.toLowerCase());
      continue;
    }
    if (!inSection) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    result[line.slice(0, eq).trim().toLowerCase()] = line.slice(eq + 1).trim();
  }
  return result;
}

export function resolveCredentials(profile?: string): Credentials | null {
  const env = process.env;
  if (env.AWS_ACCESS_KEY_ID && env.AWS_SECRET_ACCESS_KEY) {
    return {
      accessKeyId: env.AWS_ACCESS_KEY_ID,
      secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
      sessionToken: env.AWS_SESSION_TOKEN,
      source: "env",
    };
  }

  const wanted = profile || env.AWS_PROFILE || "default";
  const files = [
    env.AWS_SHARED_CREDENTIALS_FILE,
    path.join(os.homedir(), ".aws", "credentials"),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const file of files) {
    try {
      if (!fs.existsSync(file)) continue;
      const parsed = parseIniProfile(fs.readFileSync(file, "utf8"), wanted);
      if (parsed.aws_access_key_id && parsed.aws_secret_access_key) {
        return {
          accessKeyId: parsed.aws_access_key_id,
          secretAccessKey: parsed.aws_secret_access_key,
          sessionToken: parsed.aws_session_token,
          source: "aws-file",
        };
      }
    } catch {
      // Unreadable credential files are reported by the caller as "no credentials".
    }
  }
  return null;
}

/** Redacted identity label for evidence, e.g. "env (AKIA…4F2C)". */
export function credentialLabel(credentials: Credentials | null): string {
  if (!credentials) return "anonymous";
  const id = credentials.accessKeyId;
  const tail = id.length > 6 ? id.slice(-4) : "";
  return `${credentials.source} (${id.slice(0, 4)}…${tail})`;
}
