# Diagnosis Report Template

## Usage

This is the standard diagnostic report template used by all StorageOps specialist
Skills. It provides a structured, evidence-based format for presenting diagnostic
findings.

---

# Diagnosis Report

**Report ID:** STORAGEOPS-DIAG-XXXX
**Generated:** YYYY-MM-DD HH:MM UTC
**Category:** [primary_category] / [subcategory]
**Severity:** Critical | High | Medium | Low
**Confidence:** [0.0–1.0]

---

## Summary

[One paragraph describing the issue, the primary finding, and the impact.
This section should be understandable by both technical and non-technical readers.]

---

## Symptoms

### User Report
[What the user described, in their own words if available.]

### Observed Symptoms
- **Error messages:** [Exact error messages, status codes, response bodies]
- **Timing:** [When it started, frequency, pattern]
- **Scope:** [Affected buckets, objects, operations, users]
- **Environment:** [Provider, region, tool/version, access path]

### Impact Assessment
- [Current operational impact]
- [Potential escalation if unresolved]

---

## Diagnosis Conclusion

### Primary Root Cause
[Detailed explanation of the primary root cause. This should cite specific evidence.]

### Contributing Factors
- [Factor 1 — explanation and evidence]
- [Factor 2 — explanation and evidence]
- [Factors ruled out — explanation for why]

### Classification
- **Category:** [from issue taxonomy]
- **Subcategory:** [if applicable]
- **Root cause type:** [e.g., misconfiguration, provider behavior, workload pattern, etc.]

---

## Confidence Assessment

| Aspect | Assessment |
|---|---|
| Overall confidence | [0.0–1.0] |
| Evidence quality | Sufficient / Partial / Insufficient |
| Factors increasing confidence | [List factors] |
| Factors decreasing confidence | [List factors limiting certainty] |
| Additional evidence needed | [What would increase confidence] |

### Diagnostic Limitations & Blind Spots

[Declare known limitations and blind spots in this diagnosis. Must be honestly noted — do not conceal them to inflate confidence.]
- [Limitation 1: e.g., "CloudTrail audit logs not included; API operations may exist that are not captured in logs"]
- [Limitation 2: e.g., "Based on sampled time window only; does not reflect intraday/intraweek traffic variation"]
- [Blind spot 1: e.g., "Cold data that has never been read is outside this analysis scope; actual cost-saving potential may be larger"]

---

## Key Evidence

| # | Evidence | Source | Type | Relevance |
|---|---|---|---|---|
| 1 | [Description of evidence] | [Where it came from — log file, error message, config] | log / error / config / measurement | [Why this matters] |
| 2 | ... | ... | ... | ... |

---

## Root Cause Ranking

1. **[Root Cause 1]** — Confidence: [X%]
   - Evidence: [citation to evidence table]
   - Mechanism: [How this causes the symptoms]
2. **[Root Cause 2]** — Confidence: [Y%]
   - Evidence: [citation]
   - Mechanism: [explanation]
3. ...

---

## Validation Commands

Commands that can be used to validate the diagnosis. All are read-only unless
marked `manual-only`.

```bash
# Check [aspect 1]
<read-only command>

# Check [aspect 2]
<read-only command>

# [Destructive/test command] (manual-only: requires confirmation)
# manual-only: <command>
```

---

## Remediation Recommendations

### Recommendation 1: [Title] (Recommended)
- **Action:** [What to do]
- **Expected outcome:** [What should improve]
- **Risk:** [Low / Medium / High] — [explanation of risks]
- **Rollback:** [How to undo if needed]
- **Status:** `manual-only` — requires review before applying

### Recommendation 2: [Title]
- ...

---

## Risk Notes

### Current State Risks
- [Risk of not addressing the issue]
- [Potential for escalation]

### Change Risks
- [Risks associated with each recommendation]
- [Interactions with other systems or configurations]
- [Compatibility concerns]

### Security Considerations
- [Any security implications of the findings or recommendations]
- [Secret exposure: Yes / No — if yes, all redacted]

---

## Next-Step Checklist

- [ ] **Action item 1** — Rationale and expected outcome
- [ ] **Action item 2** — Rationale and expected outcome
- [ ] **Validate fix** — Use validation commands above to confirm resolution
- [ ] **Document results** — Update this report or create a follow-up note
- [ ] **Consider golden case** — Is this issue a candidate for `storageops-eval-golden-cases`?

---

## Appendix

### Skills Used
- `storageops-triage`
- `[specialist-skill-name]`
- `storageops-evidence-reporting`

### References
- [Provider documentation URLs]
- [Related issues or previous reports]

### Quantified Impact

[If applicable, include a quantified impact assessment.]
- **Affected scope:** [Number of affected objects / buckets / users]
- **Estimated recovery time:** [Estimated time to fix]
- **Cost impact (estimate):** [Estimated monthly/annual financial impact; state assumed prices]

### Redaction Statement
All secrets, credentials, tokens, and Authorization headers in this report
have been redacted as `[REDACTED]`. No real credentials are exposed.

---

**END OF REPORT**
