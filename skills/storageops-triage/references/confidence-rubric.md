# Confidence Scoring Rubric

## How to Assign Confidence Scores

Confidence scores (0.0–1.0) must be evidence-based and consistent across all
StorageOps skills. Use this rubric to determine confidence level.

---

## Scoring Levels

| Score | Label | Evidence Required | When to Use |
|-------|-------|------------------|-------------|
| 0.85–1.0 | **High** | 3+ independent evidence items, all required-evidence categories filled, root cause confirmed by validation commands | All evidence aligns, no contradictions, cross-domain checks passed, provider-specific behavior documented |
| 0.70–0.85 | **Medium-High** | 2+ independent items, most required categories, root cause consistent with all available evidence | Evidence is strong but a verification command hasn't been run, OR one evidence category is inferred rather than collected |
| 0.50–0.70 | **Medium** | 1+ independent item, partial evidence, root cause is the most likely among alternatives | Evidence is suggestive but not conclusive, OR multiple root causes are possible, OR provider-specific behavior is undocumented |
| 0.30–0.50 | **Low-Medium** | Sparse evidence, root cause is speculative but fits pattern | Only error message available, no debug logs/configs; diagnosis is a best-guess based on pattern matching |
| 0.10–0.30 | **Low** | Minimal evidence, domain classification is tentative | Only user description available, no technical artifacts; or a triage-level preliminary classification |
| <0.10 | **Speculative** | No concrete evidence | Should NOT be presented as a diagnosis; return `evidence_quality: insufficient` and request more data |

## Confidence Adjustment Factors

### Factors that INCREASE confidence (+0.1 each, max +0.3):
- [ ] Root cause confirmed by running a validation command
- [ ] Alternative root causes explicitly ruled out with evidence
- [ ] Provider-specific behavior matches documented quirks in `references/provider-quirks/`
- [ ] Issue is reproducible with provided steps
- [ ] Temporal pattern matches known behavior (e.g., batch job at specific hour)

### Factors that DECREASE confidence (-0.1 each):
- [ ] Evidence from only one source (e.g., only error message, no debug log)
- [ ] No validation command has been run
- [ ] Provider behavior not documented in quirks references
- [ ] Cross-domain dependency not verified (e.g., network not checked)
- [ ] Data window insufficient for the diagnostic domain
- [ ] Evidence is inferred rather than directly observed (e.g., "user says it was slow" without timing data)

## Hard Caps (evidence-first)

These caps override the scoring table and the adjustment factors above. They
cannot be bought back with INCREASE factors:

- **Uninspected decisive artifact → confidence ≤ 0.50.** If an artifact that
  would confirm or refute the root cause is available but has not been examined
  (the failing script, the full error body, the request that failed, the config
  in play), confidence MUST NOT exceed 0.50. Report it as a leading hypothesis
  and inspect the artifact before raising confidence.
- **Resemblance is not evidence.** Matching an error string to a known signature,
  or recalling a similar prior case from memory, does not by itself raise
  confidence above 0.50. The matching artifact must be inspected to confirm the
  mechanism, not just the surface symptom.
- **No falsifier considered → cap at Medium (0.70).** If you cannot name the
  evidence that would overturn the diagnosis, you have not tested it; do not
  present it as High.

## Example Assessments

### Example 1: rclone corrupted on transfer
- Evidence: rclone debug log showing MD5 mismatch + config file + tool version + rclone reference doc
- Validation: ETag format analysis confirms multipart vs single PUT discrepancy
- Cross-domain: Network/performance ruled out (RTT normal)
- Provider-quirks: BOS ETag behavior documented
- **Confidence: 0.90** (high — 4 evidence items, validation run, quirks match)

### Example 2: Slow upload, no baseline
- Evidence: user description only ("uploads are slow"), no timing data, no network baseline
- Cross-domain: not checked
- **Confidence: 0.25** (low — user description only, no measurement)

### Example 3: 403 AccessDenied with policy JSON
- Evidence: 403 XML response + IAM policy + bucket policy + user ARN
- Validation: policy permission evaluator confirms Allow exists but condition key SourceIP restricts
- Cross-domain: signature verified correct
- **Confidence: 0.88** (high — full policy, validation confirmed, cross-domain clear)

### Example 4: Replication lag suspected, no CloudTrail
- Evidence: source and replica object comparison (5 objects), replication config
- Missing: no CloudTrail/audit logs, no CloudWatch replication metrics
- Cross-domain: network RTT checked
- **Confidence: 0.55** (medium — object-level evidence present but no replication API logs)

### Example 5: BadDigest on a custom sync script (resemblance trap)
- Surface: the error string resembles data corruption / multipart ETag mismatch
- Available but uninspected: the sync script that built and signed the request
- Premature read: 0.85 ("looks like a checksum problem")
- **Correct: cap at 0.50 until the script is read.** Reading it shows the payload
  `x-amz-content-sha256` is computed over the uncompressed bytes while a gzipped
  body with `Content-Encoding: gzip` is sent.
- **Confidence: 0.88** — but only *after* the script confirms the mechanism, not
  from the error string alone.

## Using the Rubric

1. After completing diagnosis workflow, count independent evidence items.
2. Start with base confidence from the scoring table above.
3. Apply adjustment factors (+/- 0.1 each).
4. Cap adjustments at ±0.3 total.
5. If final confidence < 0.50, explicitly state "further evidence needed" and list what to collect.
6. Never artificially inflate confidence — honest uncertainty is better than wrong certainty.
