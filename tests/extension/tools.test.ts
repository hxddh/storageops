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
