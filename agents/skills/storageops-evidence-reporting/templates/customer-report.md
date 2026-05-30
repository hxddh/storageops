# Customer Report Template

## Usage

Use this template when communicating diagnostic findings to a customer or non-technical
stakeholder. Keep language accessible. Focus on impact, timeline, and resolution.

---

# StorageOps Diagnostic Report — Customer Summary

**Date:** YYYY-MM-DD
**Reference:** STORAGEOPS-XXXX
**Severity:** (Critical / High / Medium / Low)

## Executive Summary

One paragraph summary of the issue, its impact on the customer, and the primary
finding. Avoid technical jargon. Focus on business impact.

## What We Observed

Brief, non-technical description of the symptoms:
- What the customer experienced (slow performance, access denied, etc.).
- When it started and how often it occurs.
- Which operations or resources are affected.

## What We Found

Summary of the diagnosis in accessible terms:
- The primary root cause described without technical jargon.
- Why it happened.
- Whether it was a configuration issue, a provider behavior difference, or a
  workload pattern mismatch.

## Impact Assessment

- Current impact on the customer's operations.
- Potential impact if left unresolved.
- Whether other resources or users are affected.

## Recommendations

Numbered list of recommended actions, from simplest to most complex:
1. **Action** — What to do, in plain language. Expected benefit.
2. **Action** — ...

All actions that involve configuration changes are marked: **(requires review before applying)**

## Estimated Timeline

- Time to implement recommendations.
- Time to see improvement.
- Any dependencies on provider support or other teams.

## Next Steps

- [ ] Customer to review recommendations.
- [ ] Customer to provide additional data if needed (list specific items).
- [ ] Follow-up scheduled for: [date or timeframe].

## Contact

For questions about this report: [internal team or reference]

---

**CONFIDENTIAL:** This report contains diagnostic findings specific to the
customer's environment. Do not share without authorization. All credentials
and sensitive values have been redacted as `[REDACTED]`.
