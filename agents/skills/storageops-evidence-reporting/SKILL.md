---
name: storageops-evidence-reporting
description: >
  Produce structured diagnostic reports for object storage issues:
  customer-facing reports, internal engineering analysis notes,
  reproduction checklists, and standardized diagnosis reports with
  evidence tables, root cause ranking, confidence scoring, validation
  commands, remediation plans, and next-step checklists. Use after
  completing diagnosis with one or more specialist Skills, when the
  user requests a formal written report, or when documenting findings
  for handoff to another team.
maturity: core
mode: light_heavy
estimated_tokens: 2000
trigger_keywords:
  - report
  - write up
  - document
  - customer summary
  - diagnosis report
  - reproduction steps
recommended_tools:
  - scan_secrets
  - search_memory
---

# Evidence-Based Reporting

## When to use this skill

- After completing diagnosis with one or more specialist Skills.
- When the user requests a formal diagnostic report.
- When findings need to be handed off to another team (engineering, support, customer).
- When documenting a complex issue for future reference or regression testing.
- When creating a reproduction guide for an issue.
- When summarizing diagnostic findings for a non-technical audience (customer report).

## Do not use this skill when

- Diagnosis is not yet complete → return to the appropriate specialist Skill for more analysis.
- The user only wants a quick answer, not a formal report.
- The issue is trivially resolved and needs no documentation.
- You are still collecting evidence → complete triage first.

## Safety rules

- All report content must be evidence-based. Never fabricate or assume findings.
- Never include secrets in reports. Redact AK/SK/token/cookie/Authorization as `[REDACTED]`.
- Never include raw credentials in command examples. Use placeholders.
- Mark all remediation steps as `manual-only` unless they are read-only validations.
- Include risk warnings for any recommended changes.
- Do not include destructive or security-weakening recommendations.
- Label confidence levels honestly — do not overstate certainty.

## Recommended Tool Calls

| Tool | When to call | Example input |
|---|---|---|
| `scan_secrets` | Before finalizing any report, scan all content for credentials | `{"text": "<full report draft>"}` |
| `search_memory` | At start, retrieve prior diagnostic sessions for context | `{"query": "prior diagnosis <category> <symptom>"}` |

## Required evidence

Before generating a report, verify:
1. All diagnostic conclusions cite specific evidence.
2. Root cause(s) are ranked by confidence.
3. Validation commands are included and read-only by default.
4. Risk notes cover the impact of recommendations.
5. No secrets remain in the report.

## Report Templates

### 1. Customer Report (`templates/customer-report.md`)
- For external/customer audiences.
- Non-technical language where possible.
- Focus on impact, resolution, and timeline.
- Minimize internal detail.

### 2. Internal Engineering Note (`templates/internal-engineering-note.md`)
- For internal engineering teams.
- Full technical detail.
- Include all evidence, analysis steps, and rejected hypotheses.
- May include speculation clearly labeled as such.

### 3. Reproduction Checklist (`templates/reproduction-checklist.md`)
- Step-by-step reproduction guide.
- Required environment and data.
- Expected result at each step.
- Common pitfalls.

### 4. Diagnosis Report (`templates/diagnosis-report.md`)
- Standard format for general diagnostic output.
- Evidence table, root cause ranking, validation commands.
- Used by most specialist Skills as default output format.

## Workflow

> **Mode**: This skill supports **Light** (quick classification, <2 min) and **Heavy** (full deep-dive, up to 10 min) modes.
> Light mode: steps 1–3 only. Heavy mode: all steps.

> **Thinking framework**: Before outputting, reason through: (1) What evidence is present? (2) What is the most likely root cause? (3) What am I uncertain about? (4) What is the minimum next action?

### Step 1: Collect Diagnostic Outputs
Gather the structured YAML/JSON outputs from all specialist skills invoked during diagnosis.
Each output should include `category`, `confidence`, `severity`, `root_cause_type`, and `evidence` items.

### Step 2: Select Report Template
Choose the appropriate template based on audience:
- `templates/customer-report.md` — External/customer-facing (non-technical language)
- `templates/internal-engineering-note.md` — Internal engineering team (full technical detail)
- `templates/reproduction-checklist.md` — Step-by-step reproduction guide
- `templates/diagnosis-report.md` — Standard comprehensive diagnostic report (default)

### Step 3: Run Redaction Checklist
Before writing any content, scan ALL evidence for secrets:
- [ ] AK/SK values → `[REDACTED]`
- [ ] Authorization headers → `[REDACTED]`
- [ ] Session tokens → `[REDACTED]`
- [ ] IAM/KMS ARN account IDs → mask account portion
- [ ] Real IP addresses → mask if identifying user infrastructure
See `references/reporting-best-practices.md` for the complete checklist.

### Step 4: Populate Report Sections
Fill each section from the template, citing evidence items by reference number (E-1, E-2, ...).
See `references/reporting-best-practices.md` for section requirements and anti-patterns.

### Step 5: Apply Confidence Scoring (if not already done)
Use the rubric from `storageops-triage/references/confidence-rubric.md`:
- Count independent evidence items → base score
- Apply adjustment factors (+/- 0.1 each, max ±0.3)
- If final confidence < 0.50, add explicit "Further evidence needed" section

### Step 6: Quality Gates
Before finalizing, verify:
1. **Evidence Gate:** ≥2 independent evidence items support primary root cause
2. **Safety Gate:** Zero secrets, zero unsafe recommendations unmasked
3. **Completeness Gate:** All Minimum Required Sections present
4. **Confidence Gate:** Score is honest, limitations declared
5. **Actionability Gate:** ≥1 concrete `manual-only` recommendation

## Diagnosis Report Structure

Every diagnosis report MUST include these sections:

```markdown
# 诊断报告 (Diagnosis Report)

## 摘要 (Summary)
- One paragraph summarizing the issue and the primary finding.

## 问题现象 (Symptoms)
- What the user observed.
- Error messages, status codes, timing.
- Scope and impact.

## 诊断结论 (Diagnosis Conclusion)
- Primary root cause(s).
- Confidence level with justification.
- Category and subcategory.

## 置信度 (Confidence)
- Overall confidence: <0.0–1.0>
- Factors increasing confidence.
- Factors decreasing confidence.
- Additional evidence needed to increase confidence.

## 关键证据 (Key Evidence)
- Evidence table:

| # | Evidence | Source | Relevance |
|---|---|---|---|
| 1 | Description | Where it came from | Why it matters |
| 2 | ... | ... | ... |

## 根因排序 (Root Cause Ranking)
1. **Root Cause 1** (confidence: X%) — Description, evidence.
2. **Root Cause 2** (confidence: Y%) — Description, evidence.
...

## 验证命令 (Validation Commands)
- Commands to verify the diagnosis (all read-only or marked manual-only).

## 修复建议 (Remediation Recommendations)
- Ranked by effectiveness and risk.
- Each marked as manual-only if destructive or mutating.
- Include risk notes for each recommendation.

## 风险提示 (Risk Notes)
- Risks of the current state (what happens if not fixed).
- Risks of proposed changes.
- Security considerations.

## 后续排查清单 (Next-Step Checklist)
- [ ] Action item 1 — rationale
- [ ] Action item 2 — rationale
```

## Output requirements

The report must include in its structured output:

```yaml
# Output Envelope v2
report_type: customer_report | internal_engineering_note | reproduction_checklist | diagnosis_report
category: <from specialist Skill>
confidence: <0.0–1.0>
confidence_factors:
  - factor: evidence_specificity
    weight: 0.5
    note: "exact error code and context vs. vague description"
  - factor: evidence_completeness
    weight: 0.3
    note: "required evidence categories present"
  - factor: cross_domain_exclusion
    weight: 0.2
    note: "competing hypotheses ruled out"
severity: critical | high | medium | low
evidence_count: <number of evidence items>
evidence_quality_score: <0.0–1.0>
unsafe_recommendations: <count of manual-only items>
secret_scan_passed: true | false
next_actions:
  - type: request_evidence | invoke_skill | ask_user
    target: <skill_name or evidence_type>
    reason: <why>
    priority: 1
```

## Common mistakes to avoid

1. **Writing reports without evidence** — Every claim must cite evidence.
2. **Overstating confidence** — Be honest about uncertainty.
3. **Including secrets in reports** — Always scan before finalizing.
4. **Recommending unsafe actions without manual-only label** — Any destructive change must be flagged.
5. **Skipping the next-step checklist** — Reports should be actionable.
6. **Using inappropriate template for audience** — Customer report ≠ engineering note.
7. **Omitting risk notes** — Every recommendation has trade-offs.
