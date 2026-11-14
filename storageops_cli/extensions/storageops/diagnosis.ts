/**
 * Diagnosis contract: shape, deterministic validation, and rendering.
 *
 * The validator is the runtime gate the skills promise: no root cause outside
 * the shared contract, no assertion without evidence, no agent-applied fix.
 */

import { CONTRACT_VERSION, DOMAINS, type DomainContract } from "./contract.generated.ts";

export type Remedy = {
  action: string;
  risk: "none" | "low" | "medium" | "high";
  reversible: boolean;
  apply_by: "human" | "agent";
};

export type DiagnosisInput = {
  route: string;
  provider?: string;
  confidence: number;
  primary: { root_cause_type: string; affected_layer: string; mechanism: string };
  alternatives?: Array<{ root_cause_type: string; why_rejected: string }>;
  evidence: Array<{ id: string; claim: string }>;
  remediation: Remedy[];
  falsifiers?: string[];
  open_questions?: string[];
};

export type Diagnosis = DiagnosisInput & {
  domain: string;
  root_cause_id: string;
  evidence_quality: "sufficient" | "partial";
  contract_version: string;
};

export type Validation =
  | { ok: true; diagnosis: Diagnosis; markdown: string }
  | { ok: false; errors: string[]; allowed_root_causes?: string[] };

const RISKS = new Set(["none", "low", "medium", "high"]);

function normalize(term: string): string {
  return (term || "").trim().toLowerCase().replace(/_/g, "-");
}

export function domainForRoute(route: string): [string, DomainContract] | null {
  const key = (route || "").trim();
  if (DOMAINS[key]) return [key, DOMAINS[key]];
  for (const [domain, spec] of Object.entries(DOMAINS)) {
    if (spec.skill === key) return [domain, spec];
  }
  return null;
}

export function resolveRootCause(term: string, domain: string): string | null {
  const spec = DOMAINS[domain];
  if (!spec) return null;
  const key = normalize(term);
  if (spec.ids.includes(key)) return key;
  return spec.aliases[key] || null;
}

export function routes(): string[] {
  return Object.values(DOMAINS).map(spec => spec.skill);
}

export function validateDiagnosis(
  input: DiagnosisInput,
  evidenceIds: Set<string>,
): Validation {
  const errors: string[] = [];

  const route = domainForRoute(input.route);
  if (!route) {
    errors.push(`route must be one of: ${Array.from(new Set(routes())).join(", ")}`);
  }
  const [domain, spec] = route || ["", { skill: "", ids: [], aliases: {} }];

  const rootCause = route ? resolveRootCause(input.primary?.root_cause_type || "", domain) : null;
  if (route && !rootCause) {
    errors.push(
      `primary.root_cause_type "${input.primary?.root_cause_type || ""}" is not in ${domain}; use one of: ${spec.ids.join(", ")}`,
    );
  }

  if (!input.primary?.mechanism || input.primary.mechanism.trim().length < 12) {
    errors.push("primary.mechanism must explain the failure in at least a sentence");
  }
  if (!input.primary?.affected_layer) {
    errors.push("primary.affected_layer is required (e.g. client-sdk, bucket-policy, network-path)");
  }

  const confidence = Number(input.confidence);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    errors.push("confidence must be a number between 0 and 1");
  }

  const evidence = input.evidence || [];
  if (evidence.length === 0) {
    errors.push("evidence must cite at least one probe result (ids look like ev_1)");
  }
  for (const item of evidence) {
    if (!item?.id || !evidenceIds.has(item.id)) {
      errors.push(`evidence id "${item?.id || ""}" was not produced in this session; call a probe first`);
    }
    if (!item?.claim || item.claim.trim().length < 8) {
      errors.push(`evidence ${item?.id || "?"}: claim must state what the evidence shows`);
    }
  }

  const remediation = input.remediation || [];
  if (remediation.length === 0) {
    errors.push("remediation must contain at least one manual step");
  }
  for (const [index, step] of remediation.entries()) {
    if (!step?.action || step.action.trim().length < 6) {
      errors.push(`remediation[${index}].action is required`);
    }
    if (!RISKS.has(step?.risk)) {
      errors.push(`remediation[${index}].risk must be one of none|low|medium|high`);
    }
    if (step?.apply_by !== "human") {
      errors.push(`remediation[${index}].apply_by must be "human"; StorageOps does not change infrastructure`);
    }
  }

  if (!input.falsifiers || input.falsifiers.length === 0) {
    errors.push("falsifiers must name at least one observation that would disprove the diagnosis");
  }

  if (errors.length) {
    return { ok: false, errors, allowed_root_causes: route ? spec.ids : undefined };
  }

  const diagnosis: Diagnosis = {
    ...input,
    domain,
    root_cause_id: rootCause as string,
    evidence_quality: evidence.length >= 3 ? "sufficient" : "partial",
    contract_version: CONTRACT_VERSION,
  };
  return { ok: true, diagnosis, markdown: renderDiagnosis(diagnosis) };
}

export function renderDiagnosis(diagnosis: Diagnosis): string {
  const lines: string[] = [];
  lines.push("## Summary");
  lines.push("");
  lines.push(`**Route**: ${diagnosis.route}`);
  lines.push(`**Confidence**: ${diagnosis.confidence.toFixed(2)}`);
  lines.push(`**Evidence Quality**: ${diagnosis.evidence_quality}`);
  lines.push(
    `**Primary Diagnosis**: root_cause_type=${diagnosis.root_cause_id}, affected_layer=${diagnosis.primary.affected_layer}`,
  );
  if (diagnosis.provider) lines.push(`**Provider**: ${diagnosis.provider}`);
  lines.push("");
  lines.push(diagnosis.primary.mechanism.trim());
  lines.push("");
  lines.push("## Key Evidence");
  lines.push("");
  for (const item of diagnosis.evidence) {
    lines.push(`- [${item.id}] ${item.claim.trim()}`);
  }
  lines.push("");
  lines.push("## Remediation");
  lines.push("");
  diagnosis.remediation.forEach((step, index) => {
    const marks = [step.risk === "none" ? null : `risk: ${step.risk}`, step.reversible ? "reversible" : "irreversible"]
      .filter(Boolean)
      .join(", ");
    lines.push(`${index + 1}. **${step.action.trim()}** (manual${marks ? ` — ${marks}` : ""})`);
  });
  if (diagnosis.alternatives?.length) {
    lines.push("");
    lines.push("## Alternatives Considered");
    lines.push("");
    for (const alt of diagnosis.alternatives) {
      lines.push(`- **${alt.root_cause_type}** — rejected: ${alt.why_rejected}`);
    }
  }
  lines.push("");
  lines.push("## What Would Falsify This");
  lines.push("");
  for (const item of diagnosis.falsifiers || []) lines.push(`- ${item}`);
  if (diagnosis.open_questions?.length) {
    lines.push("");
    lines.push("## Risks / Open Questions");
    lines.push("");
    for (const item of diagnosis.open_questions) lines.push(`- ${item}`);
  }
  return lines.join("\n").trimEnd() + "\n";
}
