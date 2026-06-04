import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import {
  redactText,
  detectDomain,
  searchTokens,
  searchMemory,
  validateTraceCommand,
  traceRejectionGuidance,
  sanitizeResponseHeaders,
} from "../../storageops_cli/extensions/storageops.ts";

test("redactText redacts AWS key, presigned signature, GCP and Azure keys", () => {
  const r = redactText(
    "AccessKeyId=AKIAIOSFODNN7EXAMPLE " +
      "url?X-Amz-Signature=abcd1234ef567890abcd1234 " +
      '"private_key_id": "a1b2c3d4e5f6a7b8" ' +
      "AccountKey=YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXowMTIzNDU2Nzg5MA==",
  );
  assert.ok(r.findings.length >= 3, "should detect multiple secret classes");
  assert.ok(!r.redacted.includes("AKIAIOSFODNN7EXAMPLE"), "AWS key redacted");
  assert.ok(r.redacted.includes("[REDACTED]"));
});

test("detectDomain routes 429 to performance and Chinese access-denied to security", () => {
  const perf = detectDomain("s5cmd sync reports 429 SlowDown");
  assert.equal(perf[0].recommended_skill, "storageops-performance-diagnosis");
  const sec = detectDomain("访问被拒绝，权限不足");
  assert.equal(sec[0].recommended_skill, "storageops-security-iam-policy");
});

test("detectDomain routes BOS BadDigest payload-hash cases to protocol without substring pollution", () => {
  const results = detectDomain(
    "archive object upload failed through the bcebos backend: BadDigestSHA256, " +
      "x-bce-content-sha256 mismatch on bos:/bucket/key.",
  );

  assert.equal(results[0].recommended_skill, "storageops-s3-protocol-compatibility");
  assert.ok(results[0].subdomains.includes("payload_digest"));
  assert.ok(results[0].subdomains.includes("protocol_header"));
  assert.equal(results.some(r => r.recommended_skill === "storageops-bigdata-pipeline"), false);
});

test("detectDomain does not classify BOS URI or bcebos backend as bcecmd", () => {
  const results = detectDomain("bcebos backend reports BadDigestSHA256 for bos:/bucket/key");
  assert.equal(results.some(r => r.recommended_skill === "storageops-cli-sdk-diagnosis"), false);
});

test("detectDomain does not misroute substrings like jobs:/blobs: to obsutil", () => {
  const noise = detectDomain("scheduler listing jobs: 5 failed; blobs: pending cleanup");
  const obsHit = noise.find(r => r.recommended_skill === "storageops-cli-sdk-diagnosis");
  assert.ok(!obsHit || !obsHit.subdomains.includes("obsutil"), "jobs:/blobs: must not match obsutil");
  // A real Huawei OBS URI still routes to the cli-sdk obsutil subdomain.
  const real = detectDomain("obsutil cp obs://bucket/key failed");
  assert.equal(real[0].recommended_skill, "storageops-cli-sdk-diagnosis");
  assert.ok(real[0].subdomains.includes("obsutil"));
});

test("detectDomain does not misroute on bare-substring noise (over-broad signature guard)", () => {
  const hasSub = (text: string, skill: string, sub: string) =>
    detectDomain(text).some(r => r.recommended_skill === skill && r.subdomains.includes(sub));

  // Benign/cross-domain text must NOT trip these formerly over-broad signatures.
  assert.equal(hasSub("rclone version 1.65 finished the copy", "storageops-replication-versioning", "versioning"), false, "'version' must not match versioning");
  assert.equal(hasSub("retry the upload in the event of a timeout", "storageops-event-notification", "event"), false, "'event' must not match notification");
  assert.equal(hasSub("results are uncertain, please re-check", "storageops-network-endpoint-access", "tls"), false, "'uncertain' must not match cert");

  // Legitimate routing must still work after tightening.
  assert.ok(hasSub("S3 Versioning is suspended; a DeleteMarker was created", "storageops-replication-versioning", "versioning"), "real versioning still routes");
  assert.ok(hasSub("configure bucket event notification routing to SQS", "storageops-event-notification", "event"), "real event notification still routes");
  assert.ok(hasSub("the TLS certificate expired", "storageops-network-endpoint-access", "tls"), "real TLS cert still routes");
});

test("detectDomain recalls protocol error codes and stops RequestExpired leaking to lifecycle", () => {
  const top = (t: string) => detectDomain(t)[0]?.recommended_skill;
  for (const code of ["RequestTimeTooSkewed", "EntityTooLarge", "EntityTooSmall", "NotImplemented", "MissingContentLength", "PreconditionFailed"]) {
    assert.equal(top(`S3 error: ${code}`), "storageops-s3-protocol-compatibility", `${code} should route to protocol`);
  }
  // RequestExpired must route to protocol, not lifecycle ("expir" was over-broad).
  const r = detectDomain("the presigned PUT failed with RequestExpired");
  assert.equal(r[0]?.recommended_skill, "storageops-s3-protocol-compatibility");
  assert.equal(r.some(x => x.recommended_skill === "storageops-lifecycle-cost"), false, "RequestExpired must not score lifecycle");
  // Real lifecycle expiration language still routes to lifecycle.
  assert.ok(detectDomain("objects expire after the lifecycle expiration rule").some(x => x.recommended_skill === "storageops-lifecycle-cost"));
});

test("redactText redacts the SigV4 Authorization signature but keeps credential scope and digests", () => {
  const r = redactText(
    "Authorization: AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20260604/us-east-1/s3/aws4_request, " +
      "Signature=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n" +
      "x-amz-content-sha256: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f00112",
  );
  assert.ok(!/Signature=deadbeef/.test(r.redacted), "SigV4 signature value is redacted");
  // Credential scope (region/service/date) stays visible — it is diagnostic evidence.
  assert.ok(r.redacted.includes("us-east-1") && r.redacted.includes("aws4_request"), "credential scope preserved");
  // The payload hash must NOT be over-redacted (write-side diagnosis depends on it).
  assert.ok(r.redacted.includes("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f00112"), "content-sha256 preserved");
});

test("searchTokens emits CJK bigrams", () => {
  const toks = searchTokens("费用归因分析");
  assert.ok(toks.includes("费用") && toks.includes("归因"));
});

test("searchMemory recalls a session in a nested scope subdir and dedupes per session", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "so-mem-"));
  const scope = path.join(dir, "sessions", "--root--");
  fs.mkdirSync(scope, { recursive: true });
  fs.writeFileSync(
    path.join(scope, "s1.jsonl"),
    '{"role":"user","content":"investigating CLOUD-MULTI-0426 replication lag"}\n',
  );
  fs.writeFileSync(
    path.join(scope, "s1.meta.json"),
    JSON.stringify({ id: "s1", summary: "CLOUD-MULTI-0426 issue", updated: "2026-06-01" }),
  );
  process.env.PI_CODING_AGENT_DIR = dir;
  const res = searchMemory("CLOUD-MULTI-0426");
  assert.ok(res.length >= 1, "recalls the nested session");
  assert.equal(res.filter(r => r.sessionId === "s1").length, 1, "deduped per session");
});

test("validateTraceCommand allows read-only and blocks unsafe commands", () => {
  assert.deepEqual(
    validateTraceCommand(["aws", "s3api", "head-object", "--bucket", "b", "--key", "k"], "s3.example.com", false),
    [],
  );
  assert.ok(validateTraceCommand(["aws", "s3api", "delete-object", "--bucket", "b"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["sh", "-c", "rm -rf /"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["curl", "https://x?X-Amz-Signature=abc"], "x", false).length > 0);
});

test("validateTraceCommand allows common read-only storage diagnostics", () => {
  for (const op of [
    "get-bucket-policy",
    "get-bucket-logging",
    "get-bucket-notification-configuration",
    "get-bucket-object-lock-configuration",
    "get-object-retention",
    "get-object-legal-hold",
    "list-object-versions",
  ]) {
    assert.deepEqual(validateTraceCommand(["aws", "s3api", op, "--bucket", "b"], "s3.example.com", false), []);
  }

  assert.deepEqual(
    validateTraceCommand(["aws", "s3api", "head-object", "--bucket", "b", "--key", "delete"], "s3.example.com", false),
    [],
    "object keys named like mutating verbs are not operations",
  );
  assert.deepEqual(
    validateTraceCommand(["rclone", "ls", "remote:sync/"], "s3.example.com", false),
    [],
    "paths named like mutating verbs are not operations",
  );
  assert.deepEqual(
    validateTraceCommand(["aws", "s3api", "head-object", "--bucket", "b", "--key", "logs/a&b.txt"], "s3.example.com", false),
    [],
    "argv parameters can contain shell metacharacters because no shell is used",
  );
});

test("validateTraceCommand rejects curl method variants without blocking host mismatch", () => {
  assert.ok(validateTraceCommand(["curl", "-XPOST", "https://s3.example.com"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["curl", "--request=POST", "https://s3.example.com"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["curl", "-X", "PUT", "https://s3.example.com"], "s3.example.com", false).length > 0);
  assert.deepEqual(validateTraceCommand(["curl", "https://other.example.com"], "s3.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["curl", "--url", "https://other.example.com"], "s3.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["curl", "-f", "https://s3.example.com"], "s3.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["curl", "-x", "http://127.0.0.1:8080", "https://s3.example.com"], "s3.example.com", false), []);
  assert.ok(validateTraceCommand(["curl", "-dhello=world", "https://s3.example.com"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["curl", "--data=hello=world", "https://s3.example.com"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["curl", "-F", "file=@a.txt", "https://s3.example.com"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["curl", "-T", "a.txt", "https://s3.example.com"], "s3.example.com", false).length > 0);
});

test("validateTraceCommand allows tightly bounded unknown client observation", () => {
  assert.deepEqual(validateTraceCommand(["python", "check_s3.py", "--bucket", "b"], "s3.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["node", "probe.js", "--endpoint", "https://s3.example.com"], "s3.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["ossutil", "stat", "oss://bucket/key"], "oss.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["coscli", "ls", "cos://bucket/prefix"], "cos.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["python", "check_s3.py", "--key", "delete"], "s3.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["node", "probe.js", "https://other.example.com"], "s3.example.com", false), []);
  assert.ok(validateTraceCommand(["python", "check_s3.py", "--method", "DELETE"], "s3.example.com", false).length > 0);
  assert.ok(validateTraceCommand(["node", "probe.js", "-XPOST"], "s3.example.com", false).length > 0);
  assert.deepEqual(validateTraceCommand(["node", "probe.js", "-x", "http://127.0.0.1:8080"], "s3.example.com", false), []);
});

test("validateTraceCommand downgrades unclassified known client commands to observation", () => {
  assert.deepEqual(validateTraceCommand(["rclone", "about", "remote:"], "s3.example.com", false), []);
  assert.deepEqual(validateTraceCommand(["mc", "du", "alias/bucket"], "s3.example.com", false), []);
  assert.ok(validateTraceCommand(["rclone", "sync", "remote:a", "remote:b"], "s3.example.com", false).length > 0);
});

test("traceRejectionGuidance redirects write rejections and stays silent for read-only", () => {
  const writeErrors = validateTraceCommand(["aws", "s3api", "put-object", "--bucket", "b"], "s3.example.com", false);
  const guidance = traceRejectionGuidance(writeErrors);
  assert.ok(guidance.includes("checksum-etag.md"), "points at the write-side evidence ladder");
  assert.ok(guidance.includes("read-only"), "tells the agent live trace stays read-only");
  // A non-write rejection (e.g. presigned material) gets no write redirect.
  const presignedErrors = validateTraceCommand(["curl", "https://x?X-Amz-Signature=abc"], "x", false);
  assert.equal(traceRejectionGuidance(presignedErrors), "");
  assert.equal(traceRejectionGuidance([]), "");
});

test("sanitizeResponseHeaders passes metadata, masks cookies, redacts presigned in location", () => {
  const out = sanitizeResponseHeaders({
    "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
    "x-bce-object-rentention-date": "Tue, 30 Jun 2026 07:03:24 GMT",
    "x-amz-checksum-sha256": "qz0H8m1n2o3p4q5r6s7t8u9v0w1x2y3z4a5b6c7d8e9=",
    "set-cookie": "session=supersecretvalue; Path=/",
    "location": "https://b.example.com/k?X-Amz-Signature=deadbeefdeadbeefdeadbeef0011",
  });
  const get = (n: string) => out.find(h => h.name === n)?.value;
  assert.equal(get("etag"), '"d41d8cd98f00b204e9800998ecf8427e"', "metadata passes through unmodified");
  assert.ok((get("x-bce-object-rentention-date") || "").includes("2026"), "retention date intact");
  assert.ok((get("x-amz-checksum-sha256") || "").includes("qz0H8m1n2o3p"), "checksum not over-redacted");
  assert.equal(get("set-cookie"), "[REDACTED]", "cookie value masked");
  assert.ok(!(get("location") || "").includes("deadbeefdeadbeef"), "presigned signature redacted in location");
});
