# Reporting Best Practices

## Evidence-Based Reporting Standards

### Golden Rules
1. **Every claim must cite evidence.** No speculative diagnosis without data backing.
2. **Confidence must be honest.** Never overstate certainty to make the report look better.
3. **Blind spots must be declared.** Every report has limits — state them explicitly.
4. **Secrets must be redacted BEFORE writing.** Scan, redact, then write — never the reverse.
5. **Recommendations must be actionable.** Vague advice like "improve performance" is useless.

## Redaction Checklist (Before Finalizing Any Report)

Run through this checklist before outputting ANY report content:

- [ ] All AK/SK values redacted as `[REDACTED]`
- [ ] All Authorization headers fully redacted
- [ ] All session tokens redacted
- [ ] All cookies with auth content redacted  
- [ ] No IAM Role ARN contains unmasked account IDs
- [ ] No KMS Key ARN contains unmasked account IDs
- [ ] No plaintext credentials in command examples (use `<your-key>` placeholders)
- [ ] No real IP addresses that could identify user infrastructure (use `10.x.x.x` for private, mask public)

## Audience-Appropriate Templates

### Customer-Facing Report
- Non-technical language
- Focus on impact and resolution timeline
- Minimize internal detail (don't mention internal tools, debugging methods)
- Never include raw log excerpts or stack traces
- Never mention "bug" in the provider unless confirmed

### Internal Engineering Note
- Full technical detail acceptable
- Include all evidence, analysis steps, and rejected hypotheses
- May include speculation clearly labeled as "Hypothesis (unverified)"
- Code snippets and raw log excerpts OK (after redaction)

### Reproduction Checklist
- Step-by-step with exact commands
- Expected result at each step
- Common pitfalls at each step
- Required environment/components listed upfront

## Report Section Requirements

### Minimum Required Sections (All Reports)
1. Summary (one paragraph, non-technical)
2. Symptoms (what was observed)
3. Diagnosis Conclusion (root cause)
4. Key Evidence (table format)
5. Validation Commands (how to verify)
6. Recommendations (ranked, with risk notes)
7. Next-Step Checklist

### Sections Required for P1+ Severity
8. Confidence Assessment (with factors)
9. Limitations & Blind Spots
10. Quantified Impact (if applicable)
11. Rollback Plan (for each recommendation)

## Anti-Patterns

| Anti-Pattern | Why It's Bad | Fix |
|---|---|---|
| "It's probably..." | Speculation without evidence | "Evidence suggests... (cite E-3)" |
| "Just delete and recreate" | Destructive without warning | Mark as `manual-only`, explain risks |
| "Increase concurrency" (alone) | May worsen throttling | Pair with rate limiting recommendation |
| "Update to latest version" (alone) | May introduce new issues | Specify exact version, test first |
| "This is definitely..." (low confidence) | Overstating certainty | "Most likely... (confidence 0.65)" |
| Report with no evidence table | Unverifiable | Always include evidence table |
| Secrets visible in report | Security incident | Run redaction checklist before output |

## Quality Gates

Before submitting any diagnosis report:

1. **Evidence Gate:** ≥2 independent evidence items support the primary root cause
2. **Safety Gate:** Zero secrets in output, zero unsafe recommendations unmasked
3. **Completeness Gate:** All Minimum Required Sections present
4. **Confidence Gate:** If confidence < 0.5, the report must explicitly state "further evidence needed" and what to collect
5. **Actionability Gate:** At least one concrete `manual-only` recommendation with specific steps
