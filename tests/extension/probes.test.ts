import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import {
  signRequest,
  parseIniProfile,
  credentialLabel,
} from "../../storageops_cli/extensions/storageops/sigv4.ts";
import { deriveFacts, parseTarget } from "../../storageops_cli/extensions/storageops/probe.ts";
import {
  validateDiagnosis,
  renderDiagnosis,
  resolveRootCause,
  domainForRoute,
} from "../../storageops_cli/extensions/storageops/diagnosis.ts";
import { recordCase, searchCases, casesDir } from "../../storageops_cli/extensions/storageops/cases.ts";
import { registerEvidence, resetEvidence } from "../../storageops_cli/extensions/storageops/evidence.ts";

// Known-answer vector computed independently with Python's hashlib/hmac from the
// SigV4 spec (not from this implementation), so a signing bug cannot agree with
// itself.
const VECTOR = {
  url: "https://examplebucket.s3.us-west-2.amazonaws.com/?list-type=2&max-keys=2",
  region: "us-west-2",
  accessKeyId: "AKIDEXAMPLE",
  secretAccessKey: "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
  date: new Date("2024-05-01T12:00:00Z"),
  signature: "201c2d44da55b974294c87d823372b5d3c5046e40a15b3dc5c343409958c685f",
  canonicalRequest:
    "GET\n/\nlist-type=2&max-keys=2\n" +
    "host:examplebucket.s3.us-west-2.amazonaws.com\n" +
    "x-amz-content-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n" +
    "x-amz-date:20240501T120000Z\n\n" +
    "host;x-amz-content-sha256;x-amz-date\n" +
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
};

test("signRequest reproduces an independently computed SigV4 signature", () => {
  const signed = signRequest({
    method: "GET",
    url: new URL(VECTOR.url),
    region: VECTOR.region,
    credentials: {
      accessKeyId: VECTOR.accessKeyId,
      secretAccessKey: VECTOR.secretAccessKey,
      source: "env",
    },
    date: VECTOR.date,
  });
  assert.equal(signed.canonicalRequest, VECTOR.canonicalRequest);
  assert.equal(signed.signature, VECTOR.signature);
  assert.equal(
    signed.headers.authorization,
    `AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20240501/us-west-2/s3/aws4_request, ` +
      `SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature=${VECTOR.signature}`,
  );
});

test("signRequest includes a session token and leaves secrets out of the label", () => {
  const signed = signRequest({
    method: "HEAD",
    url: new URL("https://bucket.s3.amazonaws.com/"),
    region: "us-east-1",
    credentials: {
      accessKeyId: "ASIAIOSFODNN7EXAMPLE",
      secretAccessKey: "secret",
      sessionToken: "token-value",
      source: "env",
    },
    date: VECTOR.date,
  });
  assert.equal(signed.headers["x-amz-security-token"], "token-value");
  assert.ok(signed.headers.authorization.includes("SignedHeaders=host;x-amz-content-sha256;x-amz-date;x-amz-security-token"));
  const label = credentialLabel({
    accessKeyId: "ASIAIOSFODNN7EXAMPLE",
    secretAccessKey: "secret",
    source: "env",
  });
  assert.equal(label, "env (ASIA…MPLE)");
  assert.ok(!label.includes("secret"));
});

test("parseIniProfile reads one profile and ignores the others", () => {
  const ini = [
    "[default]",
    "aws_access_key_id = AKIADEFAULT",
    "aws_secret_access_key = s1",
    "",
    "[profile prod]",
    "aws_access_key_id=AKIAPROD",
    "aws_secret_access_key=s2",
    "aws_session_token=t2",
  ].join("\n");
  assert.deepEqual(parseIniProfile(ini, "default"), {
    aws_access_key_id: "AKIADEFAULT",
    aws_secret_access_key: "s1",
  });
  assert.equal(parseIniProfile(ini, "prod").aws_access_key_id, "AKIAPROD");
  assert.equal(parseIniProfile(ini, "missing").aws_access_key_id, undefined);
});

test("deriveFacts turns bucket XML into the facts a diagnosis cites", () => {
  const facts = deriveFacts({
    versioning: "<VersioningConfiguration><Status>Enabled</Status></VersioningConfiguration>",
    public_access_block:
      "<PublicAccessBlockConfiguration><BlockPublicAcls>true</BlockPublicAcls>" +
      "<IgnorePublicAcls>true</IgnorePublicAcls><BlockPublicPolicy>false</BlockPublicPolicy>" +
      "<RestrictPublicBuckets>false</RestrictPublicBuckets></PublicAccessBlockConfiguration>",
    policy_status: "<PolicyStatus><IsPublic>true</IsPublic></PolicyStatus>",
    cors:
      "<CORSConfiguration><CORSRule><AllowedMethod>GET</AllowedMethod><AllowedMethod>HEAD</AllowedMethod>" +
      "<AllowedOrigin>https://app.example</AllowedOrigin></CORSRule></CORSConfiguration>",
    lifecycle:
      "<LifecycleConfiguration><Rule><Filter/><Status>Enabled</Status><Transition><Days>30</Days>" +
      "<StorageClass>GLACIER</StorageClass></Transition></Rule>" +
      "<Rule><Filter/><Status>Enabled</Status><AbortIncompleteMultipartUpload><DaysAfterInitiation>7</DaysAfterInitiation>" +
      "</AbortIncompleteMultipartUpload></Rule></LifecycleConfiguration>",
    replication:
      "<ReplicationConfiguration><Role>arn:aws:iam::1:role/r</Role><Rule><Status>Enabled</Status>" +
      "<Destination><Bucket>arn:aws:s3:::dest</Bucket></Destination></Rule></ReplicationConfiguration>",
    acl:
      "<AccessControlPolicy><Owner><ID>owner-id</ID></Owner><AccessControlList><Grant><Grantee>" +
      "<URI>http://acs.amazonaws.com/groups/global/AllUsers</URI></Grantee></Grant></AccessControlList></AccessControlPolicy>",
    policy: "{}",
  });
  assert.equal(facts.versioning, "Enabled");
  assert.deepEqual((facts.public_access_block as any).block_public_policy, false);
  assert.deepEqual(facts.policy_status, { is_public: true });
  assert.equal(facts.policy_present, true);
  assert.equal((facts.cors as any).rule_count, 1);
  assert.deepEqual((facts.cors as any).allowed_methods, ["GET", "HEAD"]);
  assert.equal((facts.lifecycle as any).rule_count, 2);
  assert.deepEqual((facts.lifecycle as any).transitions, [{ days: 30, storage_class: "GLACIER" }]);
  assert.deepEqual((facts.lifecycle as any).abort_incomplete_days, [7]);
  assert.equal((facts.replication as any).statuses[0], "Enabled");
  assert.deepEqual((facts.acl as any).public_grants, ["http://acs.amazonaws.com/groups/global/AllUsers"]);
});

test("parseTarget accepts hosts and URLs but rejects garbage", () => {
  assert.equal(parseTarget("s3.us-east-1.amazonaws.com")?.protocol, "https:");
  assert.equal(parseTarget("http://127.0.0.1:9000")?.port, "9000");
  assert.equal(parseTarget(""), null);
  assert.equal(parseTarget("::::"), null);
});

const GOOD_DIAGNOSIS = {
  route: "storageops-performance-diagnosis",
  confidence: 0.82,
  primary: {
    root_cause_type: "hot-prefix-throttling",
    affected_layer: "service",
    mechanism: "Requests concentrate on one prefix, so one partition absorbs the rate and returns SlowDown.",
  },
  evidence: [
    { id: "ev_1", claim: "429/SlowDown concentrated on data/2024/01/15 while other prefixes succeed" },
    { id: "ev_2", claim: "Bucket listing shows 80% of keys under the same prefix" },
    { id: "ev_3", claim: "Endpoint probe shows normal latency and no clock skew" },
  ],
  remediation: [
    { action: "Spread writes across more prefixes", risk: "low", reversible: true, apply_by: "human" as const },
  ],
  falsifiers: ["Throttling persists at low request rates while other prefixes fail too"],
};

test("validateDiagnosis accepts a cited diagnosis and renders canonical sections", () => {
  const verdict = validateDiagnosis(GOOD_DIAGNOSIS, new Set(["ev_1", "ev_2", "ev_3"]));
  assert.equal(verdict.ok, true);
  if (!verdict.ok) return;
  assert.equal(verdict.diagnosis.root_cause_id, "hot-prefix-throttling");
  assert.equal(verdict.diagnosis.evidence_quality, "sufficient");
  for (const section of ["## Summary", "## Key Evidence", "## Remediation", "## What Would Falsify This"]) {
    assert.ok(verdict.markdown.includes(section), `missing ${section}`);
  }
  assert.ok(verdict.markdown.includes("root_cause_type=hot-prefix-throttling"));
  assert.ok(verdict.markdown.includes("(manual — risk: low, reversible)"));
});

test("validateDiagnosis rejects uncited, out-of-contract, and agent-applied claims", () => {
  const unknownRootCause = validateDiagnosis(
    { ...GOOD_DIAGNOSIS, primary: { ...GOOD_DIAGNOSIS.primary, root_cause_type: "made-up-cause" } },
    new Set(["ev_1", "ev_2", "ev_3"]),
  );
  assert.equal(unknownRootCause.ok, false);
  if (!unknownRootCause.ok) {
    assert.ok(unknownRootCause.errors[0].includes("made-up-cause"));
    assert.ok((unknownRootCause.allowed_root_causes || []).includes("hot-prefix-throttling"));
  }

  const fabricatedEvidence = validateDiagnosis(
    { ...GOOD_DIAGNOSIS, evidence: [{ id: "ev_99", claim: "I looked at the bucket" }] },
    new Set(["ev_1"]),
  );
  assert.equal(fabricatedEvidence.ok, false);
  if (!fabricatedEvidence.ok) assert.ok(fabricatedEvidence.errors.some(e => e.includes("ev_99")));

  const agentFix = validateDiagnosis(
    {
      ...GOOD_DIAGNOSIS,
      remediation: [{ action: "Rewrite the bucket policy", risk: "high", reversible: false, apply_by: "agent" as any }],
    },
    new Set(["ev_1", "ev_2", "ev_3"]),
  );
  assert.equal(agentFix.ok, false);
  if (!agentFix.ok) assert.ok(agentFix.errors.some(e => e.includes("apply_by")));

  const noFalsifier = validateDiagnosis({ ...GOOD_DIAGNOSIS, falsifiers: [] }, new Set(["ev_1", "ev_2", "ev_3"]));
  assert.equal(noFalsifier.ok, false);
});

test("the contract resolves legacy vocabulary to canonical ids", () => {
  assert.equal(resolveRootCause("hot_prefix_throttling", "performance_throughput"), "hot-prefix-throttling");
  assert.equal(resolveRootCause("prefix-hotspot", "performance_throughput"), "hot-prefix-throttling");
  assert.equal(resolveRootCause("not-a-thing", "performance_throughput"), null);
  assert.equal(domainForRoute("storageops-security-iam-policy")?.[0], "security_iam_policy");
  assert.equal(domainForRoute("nope"), null);
});

test("recordCase writes one redacted, searchable record per diagnosis", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "storageops-cases-"));
  process.env.STORAGEOPS_CASES_DIR = dir;
  try {
    resetEvidence();
    registerEvidence("probe_bucket", "my-bucket", "facts");
    const verdict = validateDiagnosis(
      {
        ...GOOD_DIAGNOSIS,
        evidence: [{ id: "ev_1", claim: "SlowDown concentrated on one prefix" }],
        remediation: [{ action: "Rotate the prefix layout", risk: "low", reversible: true, apply_by: "human" }],
      },
      new Set(["ev_1"]),
    );
    assert.equal(verdict.ok, true);
    if (!verdict.ok) return;
    const file = recordCase(verdict.diagnosis);
    assert.ok(file && fs.existsSync(file));
    assert.equal(casesDir(), dir);
    const mode = fs.statSync(file as string).mode & 0o777;
    assert.equal(mode, 0o600);

    const hit = searchCases("SlowDown prefix", 5);
    assert.equal(hit.length, 1);
    assert.equal(hit[0].root_cause_type, "hot-prefix-throttling");
    assert.equal(searchCases("nothing-here", 5).length, 0);
  } finally {
    delete process.env.STORAGEOPS_CASES_DIR;
  }
});
