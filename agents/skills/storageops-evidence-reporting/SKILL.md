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
report_type: customer_report | internal_engineering_note | reproduction_checklist | diagnosis_report
category: <from specialist Skill>
confidence: <0.0–1.0>
severity: critical | high | medium | low
evidence_count: <number of evidence items>
unsafe_recommendations: <count of manual-only items>
secret_scan_passed: true | false
```

## Common mistakes to avoid

1. **Writing reports without evidence** — Every claim must cite evidence.
2. **Overstating confidence** — Be honest about uncertainty.
3. **Including secrets in reports** — Always scan before finalizing.
4. **Recommending unsafe actions without manual-only label** — Any destructive change must be flagged.
5. **Skipping the next-step checklist** — Reports should be actionable.
6. **Using inappropriate template for audience** — Customer report ≠ engineering note.
7. **Omitting risk notes** — Every recommendation has trade-offs.
