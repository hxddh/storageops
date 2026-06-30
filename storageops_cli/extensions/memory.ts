import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { redactText } from "./secrets.ts";

export type MemoryResult = {
  sessionId: string;
  snippet: string;
  updated: string;
  source: "summary" | "jsonl";
  score: number;
};

export function searchTokens(query: string): string[] {
  const ascii = query.toLowerCase().match(/[a-z0-9_\-:.]{3,}/g) || [];
  // CJK queries carry no ASCII word tokens, so the old tokenizer returned [] and
  // recall was empty for Chinese. Emit overlapping bigrams (and single chars for
  // length-1 runs) so Chinese memory searches recall partial matches.
  const cjkTokens: string[] = [];
  for (const run of query.match(/[一-鿿]+/g) || []) {
    if (run.length === 1) cjkTokens.push(run);
    else for (let i = 0; i < run.length - 1; i++) cjkTokens.push(run.slice(i, i + 2));
  }
  return Array.from(new Set([...ascii, ...cjkTokens])).slice(0, 12);
}

function scoreText(text: string, tokens: string[]): number {
  const lower = text.toLowerCase();
  return tokens.reduce((score, token) => score + (lower.includes(token) ? 1 : 0), 0);
}

function safeMemorySnippet(text: string): string {
  return redactText(text.replace(/\s+/g, " ").trim()).redacted.slice(0, 240);
}

const MAX_SESSION_SCAN_DEPTH = 4;
const MAX_SESSION_FILES = 200;

// Pi stores session transcripts under scope subdirectories
// (e.g. sessions/<scope>/<id>.jsonl), so a flat top-level scan misses them.
// Walk the sessions tree with bounded depth/count and index by .jsonl files;
// .meta.json is optional sibling enrichment, not required for recall.
export function collectSessionJsonl(root: string): string[] {
  const found: string[] = [];
  const walk = (dir: string, depth: number): void => {
    if (depth > MAX_SESSION_SCAN_DEPTH || found.length >= MAX_SESSION_FILES) return;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (found.length >= MAX_SESSION_FILES) return;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full, depth + 1);
      } else if (entry.isFile() && entry.name.endsWith(".jsonl")) {
        found.push(full);
      }
    }
  };
  walk(root, 0);
  return found;
}

function readSessionMeta(jsonlPath: string): { sessionId: string; summary: string; updated: string } {
  const sessionId = path.basename(jsonlPath, ".jsonl");
  const metaPath = path.join(path.dirname(jsonlPath), `${sessionId}.meta.json`);
  if (fs.existsSync(metaPath)) {
    try {
      const meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
      return {
        sessionId: meta.id || sessionId,
        summary: meta.summary || meta.name || "",
        updated: meta.updated || meta.created || "",
      };
    } catch {
      // Malformed meta; the jsonl content is still searchable.
    }
  }
  return { sessionId, summary: "", updated: "" };
}

export function searchMemory(query: string, limit: number = 5): MemoryResult[] {
  const agentDir = process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi", "agent");
  const primarySessionsDir = path.join(agentDir, "sessions");
  const fallbackSessionsDir = path.join(os.homedir(), ".pi", "agent", "sessions");
  const sessionsDir = fs.existsSync(primarySessionsDir) ? primarySessionsDir : fallbackSessionsDir;
  if (!fs.existsSync(sessionsDir)) return [];

  const tokens = searchTokens(query);
  if (tokens.length === 0) return [];
  const cappedLimit = Math.min(Math.max(limit || 5, 1), 10);

  const jsonlFiles = collectSessionJsonl(sessionsDir)
    .sort()
    .reverse()
    .slice(0, MAX_SESSION_FILES);

  const results: MemoryResult[] = [];

  for (const jsonlPath of jsonlFiles) {
    try {
      const { sessionId, summary, updated } = readSessionMeta(jsonlPath);

      const summaryScore = summary ? scoreText(summary, tokens) : 0;
      if (summaryScore > 0) {
        results.push({
          sessionId,
          snippet: safeMemorySnippet(summary),
          updated,
          source: "summary",
          score: summaryScore,
        });
      }

      const content = fs.readFileSync(jsonlPath, "utf8").slice(0, 40_000);
      const jsonlScore = scoreText(content, tokens);
      if (jsonlScore > 0) {
        const line = content.split(/\r?\n/).find(x => scoreText(x, tokens) > 0) || summary || `Session ${sessionId.slice(0, 8)}...`;
        results.push({
          sessionId,
          snippet: safeMemorySnippet(line),
          updated,
          source: "jsonl",
          score: jsonlScore,
        });
      }
    } catch {
      // Skip unreadable files
    }
  }

  // Keep only the best-scoring entry per session so one session can't occupy
  // multiple result slots (a session matching in both summary and jsonl would
  // otherwise crowd out other relevant sessions).
  const bestBySession = new Map<string, MemoryResult>();
  for (const r of results) {
    const prev = bestBySession.get(r.sessionId);
    if (!prev || r.score > prev.score) bestBySession.set(r.sessionId, r);
  }

  return Array.from(bestBySession.values())
    .sort((a, b) => b.score - a.score || String(b.updated).localeCompare(String(a.updated)))
    .slice(0, cappedLimit);
}
