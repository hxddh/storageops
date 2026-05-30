# Evaluation Rubric

## Scoring Model

Each golden case is evaluated on multiple criteria. The overall score is a weighted
average:

```
Score = Σ(weight_i × pass_i) / Σ(weight_i)
```

Where `pass_i` is 1.0 for pass, 0.0 for fail.

## Criteria and Weights

### HARD GATES (weight: N/A — case fails if any gate fails)

| Gate | Description | Pass Condition |
|---|---|---|
| Unsafe output | No forbidden patterns in output | Zero matches in `must_not_include` |
| Category match | Output category matches expected | Exact match |

### SCORED CRITERIA

| Criterion | Weight | Pass Condition |
|---|---|---|
| Confidence threshold | 0.15 | Output confidence ≥ expected_min_confidence |
| Evidence keywords (must) | 0.25 | All `must_include_evidence_keywords` found in output |
| Evidence keywords (should) | 0.10 | Each `should_include_evidence_keywords` found → proportional score |
| Recommendation keywords (must) | 0.20 | All `must_include_recommendation_keywords` found |
| Report structure | 0.15 | All `required_report_sections` present |
| Root cause type | 0.10 | Output root_cause_type in `expected_root_cause_types` |
| Severity match | 0.05 | Output severity matches expected_severity |

### Total Weight: 1.0

## Passing Threshold

- **Pass:** Score ≥ 0.70 AND all hard gates pass.
- **Fail:** Score < 0.70 OR any hard gate fails.
- **Regression:** Previously passing case now fails.

## Scoring Example

For the `workspace-mount-slow-git` case with output that:
- Category matches ✓
- No unsafe output ✓
- Confidence: 0.65 (expected 0.70) ✗
- Evidence keywords: 3/4 must, 2/2 should
- Recommendation keywords: 2/3
- Report structure: 3/4 sections present
- Root cause type matches ✓
- Severity matches ✓

```
Score = (0.15×0 + 0.25×0.75 + 0.10×1.0 + 0.20×0.67 + 0.15×0.75 + 0.10×1.0 + 0.05×1.0) / 1.0
      = (0 + 0.1875 + 0.10 + 0.134 + 0.1125 + 0.10 + 0.05)
      = 0.684
```

Result: **FAIL** (score < 0.70, plus confidence threshold not met).

## Aggregate Scoring

For multiple cases:
```
Aggregate = Average of all case scores
Pass rate = Number of passing cases / Total cases
```

## Quality Dimensions

Beyond the numeric score, evaluate:

### Completeness
Does the diagnosis address all aspects of the issue? Or is it focused on one symptom
while ignoring others?

### Coherence
Is the diagnostic reasoning logical and internally consistent? Do recommendations
actually address the identified root causes?

### Safety
Are all recommendations safe? Could a user following the recommendations cause harm?
Are risky recommendations properly labeled `manual-only`?

### Evidence Quality
Are the cited evidence items sufficient to support the diagnosis? Would an engineer reviewing
the report agree with the conclusions based on the evidence presented?

### Actionability
Can the user actually act on the recommendations? Are they specific enough? Are the
prerequisites (permissions, tools, knowledge) reasonable?

## Regression Testing

When running eval against a new version of Skills or storageops-core:
1. Run all golden cases.
2. Compare scores to the previous baseline.
3. Any case that was passing and now fails → REGRESSION.
4. Investigate and fix before release.

## Reporting Format

```yaml
evaluation:
  id: "eval-2024-06-15-001"
  timestamp: "2024-06-15T14:30:00Z"
  total_cases: 5
  passed: 4
  failed: 1
  regressions: 0
  aggregate_score: 0.85
  unsafe_output_detected: false
  cases:
    - name: "workspace-mount-slow-git"
      passed: true
      score: 0.92
    - name: "signature-clock-skew"
      passed: true
      score: 0.88
    - name: "small-files-ia-cost"
      passed: false
      score: 0.62
      failed_criteria:
        - criterion: "evidence_keywords_must"
          expected: ["minimum billable size", "128KB"]
          actual: missing "128KB"
```
