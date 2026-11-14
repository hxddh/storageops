/**
 * Case store: the durable, searchable record of past diagnoses.
 *
 * Replaces transcript grep (which matched the persisted system prompt and
 * returned noise on Pi 1.x). Each record is small, redacted, and indexed by the
 * structured fields a follow-up question actually uses.
 */

import * as fs from "fs";
import * as os from "os";
import * as path from "path";

import { redactText } from "./secrets.ts";
import { searchTokens } from "./memory.ts";
import type { Diagnosis } from "./diagnosis.ts";

export type CaseRecord = {
  case_id: string;
  created_at: string;
  route: string;
  provider?: string;
  root_cause_type: string;
  affected_layer: string;
  confidence: number;
  summary: string;
  falsifiers: string[];
  evidence_count: number;
  contract_version: string;
};

export type CaseHit = {
  case_id: string;
  created_at: string;
  route: string;
  root_cause_type: string;
  confidence: number;
  snippet: string;
  score: number;
};

const MAX_CASES_SCANNED = 500;

export function casesDir(): string {
  return process.env.STORAGEOPS_CASES_DIR || path.join(os.homedir(), ".storageops", "cases");
}

function safeWrite(dir: string, name: string, payload: unknown): string | null {
  try {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    const target = path.join(dir, name);
    fs.writeFileSync(target, JSON.stringify(payload, null, 2), { mode: 0o600 });
    return target;
  } catch {
    return null;
  }
}

export function recordCase(diagnosis: Diagnosis): string | null {
  const created = new Date().toISOString();
  const stamp = created.replace(/[:.]/g, "-");
  const record: CaseRecord = {
    case_id: `${stamp}-${diagnosis.root_cause_id}`,
    created_at: created,
    route: diagnosis.route,
    provider: diagnosis.provider,
    root_cause_type: diagnosis.root_cause_id,
    affected_layer: diagnosis.primary.affected_layer,
    confidence: diagnosis.confidence,
    summary: redactText(diagnosis.primary.mechanism).redacted.slice(0, 500),
    falsifiers: (diagnosis.falsifiers || []).map(item => redactText(item).redacted.slice(0, 200)),
    evidence_count: diagnosis.evidence.length,
    contract_version: diagnosis.contract_version,
  };
  return safeWrite(casesDir(), `${record.case_id}.json`, record);
}

export function listCases(): CaseRecord[] {
  const dir = casesDir();
  if (!fs.existsSync(dir)) return [];
  let names: string[] = [];
  try {
    names = fs
      .readdirSync(dir)
      .filter(name => name.endsWith(".json"))
      .sort()
      .reverse()
      .slice(0, MAX_CASES_SCANNED);
  } catch {
    return [];
  }
  const records: CaseRecord[] = [];
  for (const name of names) {
    try {
      const parsed = JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
      if (parsed && typeof parsed.root_cause_type === "string") records.push(parsed as CaseRecord);
    } catch {
      // Skip unreadable or half-written records.
    }
  }
  return records;
}

export function searchCases(query: string, limit = 5): CaseHit[] {
  const tokens = searchTokens(query);
  if (tokens.length === 0) return [];
  const capped = Math.min(Math.max(limit || 5, 1), 20);
  const hits: CaseHit[] = [];

  for (const record of listCases()) {
    const haystack = [
      record.route,
      record.provider || "",
      record.root_cause_type,
      record.affected_layer,
      record.summary,
      record.falsifiers.join(" "),
    ]
      .join(" ")
      .toLowerCase();
    let score = 0;
    for (const token of tokens) {
      if (haystack.includes(token)) score += 1;
      if (record.root_cause_type.toLowerCase().includes(token)) score += 2;
    }
    if (score === 0) continue;
    hits.push({
      case_id: record.case_id,
      created_at: record.created_at,
      route: record.route,
      root_cause_type: record.root_cause_type,
      confidence: record.confidence,
      snippet: redactText(record.summary).redacted.slice(0, 200),
      score,
    });
  }

  return hits.sort((a, b) => b.score - a.score || b.created_at.localeCompare(a.created_at)).slice(0, capped);
}
