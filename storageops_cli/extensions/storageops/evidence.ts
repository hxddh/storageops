/**
 * Session-scoped evidence registry.
 *
 * Every probe registers a compact, redacted record and gets an id. A diagnosis
 * may only cite ids that exist here, so a claim cannot reference evidence the
 * agent never gathered.
 */

export type EvidenceEntry = {
  id: string;
  tool: string;
  target: string;
  summary: string;
  at: string;
};

const MAX_ENTRIES = 200;

const entries = new Map<string, EvidenceEntry>();
let sequence = 0;

export function registerEvidence(tool: string, target: string, summary: string): EvidenceEntry {
  sequence += 1;
  const entry: EvidenceEntry = {
    id: `ev_${sequence}`,
    tool,
    target,
    summary: summary.slice(0, 600),
    at: new Date().toISOString(),
  };
  entries.set(entry.id, entry);
  if (entries.size > MAX_ENTRIES) {
    const oldest = entries.keys().next().value;
    if (oldest) entries.delete(oldest);
  }
  return entry;
}

export function hasEvidence(id: string): boolean {
  return entries.has(id);
}

export function getEvidence(id: string): EvidenceEntry | undefined {
  return entries.get(id);
}

export function listEvidence(): EvidenceEntry[] {
  return Array.from(entries.values());
}

export function resetEvidence(): void {
  entries.clear();
  sequence = 0;
}
