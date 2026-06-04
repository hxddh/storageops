import { test } from "node:test";
import assert from "node:assert/strict";

import { detectDomain } from "../../storageops_cli/extensions/storageops.ts";

type NegativeCase = {
  name: string;
  text: string;
  forbidden: Array<[string, string]>;
};

const NEGATIVE_CASES: NegativeCase[] = [
  {
    name: "ordinary status sync is not migration",
    text: "The internal sync status page says all background jobs are complete.",
    forbidden: [["storageops-migration-sync", "sync"]],
  },
  {
    name: "ticket transfer is not object transfer",
    text: "Please transfer ownership of the support ticket to the application team.",
    forbidden: [["storageops-migration-sync", "transfer"]],
  },
  {
    name: "mountain does not imply mount",
    text: "The Mountain View office uploaded the weekly README note.",
    forbidden: [["storageops-mount-filesystem-workspace", "mount"]],
  },
  {
    name: "version number is not versioning",
    text: "rclone version 1.65 finished copying one object.",
    forbidden: [["storageops-replication-versioning", "versioning"]],
  },
  {
    name: "event idiom is not bucket event notification",
    text: "Retry in the event of a timeout, then collect the application log.",
    forbidden: [["storageops-event-notification", "event"]],
  },
  {
    name: "uncertain does not imply certificate",
    text: "The result is uncertain, please re-check the support note.",
    forbidden: [["storageops-network-endpoint-access", "tls"]],
  },
  {
    name: "jobs and blobs do not imply obsutil",
    text: "The scheduler lists jobs: five pending, blobs: none.",
    forbidden: [["storageops-cli-sdk-diagnosis", "obsutil"]],
  },
  {
    name: "archive does not imply Hive",
    text: "The archive object failed during upload.",
    forbidden: [["storageops-bigdata-pipeline", "bigdata_engine"]],
  },
];

test("routing negative corpus blocks known bare-substring false positives", () => {
  for (const c of NEGATIVE_CASES) {
    const got = detectDomain(c.text);
    for (const [skill, subdomain] of c.forbidden) {
      assert.equal(
        got.some(r => r.recommended_skill === skill && r.subdomains.includes(subdomain)),
        false,
        `${c.name}: must not route ${subdomain} to ${skill}; got ${got.map(r => `${r.recommended_skill}:${r.subdomains.join(",")}`).join("/") || "none"}`,
      );
    }
  }
});
