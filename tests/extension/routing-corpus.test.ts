import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

import { detectDomain } from "../../storageops_cli/extensions/storageops.ts";

// Activate the golden-case corpus as a live routing-regression gate: feed every
// case's input through detect_domain and check the expected skill is recalled.
// Previously these cases (especially the routing-* ones) were never executed
// against the routing engine.

const ROOT = path.resolve(import.meta.dirname, "../..");
const CASES_DIR = path.join(ROOT, "skills/storageops-eval-golden-cases/cases");
const TAXONOMY = path.join(ROOT, "docs/skill-taxonomy.json");

// Inherently multi-signal cases where the expected skill is correctly recalled
// but not top-2 (e.g. a delete-storm access log also carries tool/event signals).
// Allowlisted to top-3 rather than over-tuning regexes to force a ranking.
const KNOWN_MULTI_SIGNAL = new Set(["access-log-delete-storm"]);
const EXPECT_TOP1 = new Set([
  "access-denied-cross-account",
  "adversarial-disable-tls",
  "bigdata-small-files-query",
  "event-notification-prefix-filter",
  "lifecycle-small-file-ia",
  "network-vpc-endpoint-dns",
  "rclone-corrupted-transfer",
  "resemblance-gzip-baddigest",
  "routing-cors-preflight",
  "routing-event-notification",
  "routing-migration-checksum",
  "routing-slow-mount-vs-throughput",
  "routing-spark-committer",
  "signature-clock-skew",
  "throttling-hot-prefix",
  "versioned-delete-marker",
]);

function categorySkill(): Record<string, string> {
  const tax = JSON.parse(fs.readFileSync(TAXONOMY, "utf8")).categories;
  const out: Record<string, string> = {};
  for (const [cat, entry] of Object.entries<any>(tax)) {
    if (entry && typeof entry.skill === "string") out[cat] = entry.skill;
  }
  return out;
}

function caseText(dir: string): string {
  const inDir = path.join(dir, "input");
  if (!fs.existsSync(inDir)) return "";
  return fs.readdirSync(inDir)
    .map(f => { try { return fs.readFileSync(path.join(inDir, f), "utf8"); } catch { return ""; } })
    .join(" ");
}

test("routing corpus: every golden case recalls its expected skill via detect_domain", () => {
  const catSkill = categorySkill();
  const cases = fs.readdirSync(CASES_DIR)
    .filter(c => fs.existsSync(path.join(CASES_DIR, c, "expected.json")));
  assert.ok(cases.length >= 30, "corpus should be non-trivial");

  for (const c of cases) {
    const expected = JSON.parse(fs.readFileSync(path.join(CASES_DIR, c, "expected.json"), "utf8"));
    const want = catSkill[expected.expected_category];
    assert.ok(want, `${c}: expected_category maps to a skill`);

    const skills = detectDomain(caseText(path.join(CASES_DIR, c))).map(r => r.recommended_skill);
    const rank = skills.indexOf(want);

    // Hard floor: the expected skill must be recalled somewhere in the ranking.
    assert.ok(rank >= 0, `${c}: expected skill ${want} not recalled (got ${skills.slice(0, 3).join("/") || "none"})`);
    // Strong check: top-2, except documented multi-signal cases (top-3).
    const limit = KNOWN_MULTI_SIGNAL.has(c) ? 3 : 2;
    assert.ok(rank < limit, `${c}: expected skill ${want} ranked ${rank + 1}, beyond top-${limit} (${skills.slice(0, 3).join("/")})`);
    if (EXPECT_TOP1.has(c)) {
      assert.equal(rank, 0, `${c}: strong signal should rank ${want} first (got ${skills.slice(0, 3).join("/")})`);
    }
  }
});
