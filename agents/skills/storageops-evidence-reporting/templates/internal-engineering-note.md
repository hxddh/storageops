# Internal Engineering Note Template

## Usage

Use this template for internal engineering documentation. Full technical detail,
including rejected hypotheses, intermediate analysis steps, and speculation (clearly
labeled). Not intended for customer-facing distribution.

---

# Engineering Note: [Issue Title]

**Date:** YYYY-MM-DD
**Author:** [Engineer / Agent]
**Reference:** STORAGEOPS-ENG-XXXX
**Related Customer Report:** STORAGEOPS-XXXX (if applicable)

## Issue Summary

Technical summary of the reported issue.

## Evidence Collected

| Type | Source | Description | Redacted? |
|---|---|---|---|
| Debug log | awscli --debug | Full request/response cycle | Yes |
| Config | ~/.aws/config | Region and endpoint | N/A |
| Error message | Application log | 403 AccessDenied XML | N/A |

## Analysis Steps

### Step 1: Initial Triage
- Classification: [category]
- Route to: [specialist Skills]
- Evidence quality at this point: [sufficient/partial/insufficient]

### Step 2: [Specialist Skill] Analysis
Detailed walkthrough of the diagnostic process.
Include specific data points, calculations, and reasoning.

### Step N: Synthesis
How the findings from different analyses combine.

## Hypotheses Evaluated

| # | Hypothesis | Evidence For | Evidence Against | Verdict |
|---|---|---|---|---|
| 1 | Clock skew causing SigV4 failure | request timestamp | system clock correct | REJECTED |
| 2 | Wrong endpoint region | config shows us-east-1, but bucket is in eu-west-1 | error message matches region mismatch | CONFIRMED |

## Root Cause Analysis

### Primary Root Cause (Confidence: X%)
Detailed technical explanation with all supporting evidence.

### Secondary Factors
Other contributing factors with lower confidence.

## Speculation (If Any)

> **SPECULATIVE:** Any hypotheses that could not be confirmed with available
> evidence. Clearly label as speculative and explain what evidence would be
> needed to confirm or reject.

## Code/Config Analysis

Relevant code snippets, configuration excerpts, or protocol traces (all secrets redacted).

## Validation Commands

Commands to verify the findings (all read-only or marked `manual-only`):

```bash
# Verify region
# manual-only: aws s3api get-bucket-location --bucket <bucket>
```

## Lessons Learned

- What pattern should be recognized faster in the future.
- What tooling or automation would have helped.
- Whether this issue should become a golden case.

## References

- Links to provider documentation.
- Links to related issues, golden cases, or previous engineering notes.
