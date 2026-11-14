import * as crypto from "crypto";

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

export type SecretFinding = {
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
