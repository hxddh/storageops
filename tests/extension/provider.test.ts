import { test } from "node:test";
import assert from "node:assert/strict";

import { detectProvider } from "../../storageops_cli/extensions/storageops.ts";

test("detectProvider identifies provider from endpoint/header/CLI and stays conservative", () => {
  // Endpoint host -> high confidence + a quirks reference where one exists.
  const bos = detectProvider("PUT https://bj.bcebos.com/bucket/key failed BadDigestSHA256");
  assert.equal(bos.provider, "bos");
  assert.equal(bos.confidence, "high");
  assert.ok(bos.quirks_ref && bos.quirks_ref.includes("provider-quirks/bos.md"));

  // Vendor header / CLI alone is enough (medium).
  assert.equal(detectProvider("response had x-oss-request-id; ossutil cp ...").provider, "oss");
  assert.equal(detectProvider("q-sign-algorithm=sha1 cos.ap-beijing.myqcloud.com").provider, "cos");
  assert.equal(detectProvider("gsutil cp file gs://b/o").provider, "gcs");

  // x-amz-* is shared by all S3-compatible providers, so it is NOT an AWS signal.
  assert.equal(detectProvider("only x-amz-content-sha256 present, no host").provider, "unknown");

  // Benign noise must not false-positive a provider.
  assert.equal(detectProvider("rclone version 1.65 finished the copy of jobs").provider, "unknown");

  // Cross-provider migration surfaces both providers in signals for the agent to weigh.
  const mig = detectProvider("migrate from bj.bcebos.com to oss-cn-hangzhou.aliyuncs.com");
  assert.ok(mig.signals.some(s => s.startsWith("bos:")) && mig.signals.some(s => s.startsWith("oss:")));
});
