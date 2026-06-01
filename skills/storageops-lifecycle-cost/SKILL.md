---
name: storageops-lifecycle-cost
description: >
  Analyze object storage lifecycle policies and costs. Covers storage class
  transitions (STANDARD→IA→ARCHIVE→DEEP_ARCHIVE), lifecycle rule evaluation,
  cost amplification from small files, minimum storage duration charges,
  retrieval fees, and intelligent tiering. Use when user asks about storage
  costs, lifecycle configuration, or tiering strategy.
maturity: stable
mode: light_heavy
estimated_tokens: 1400
trigger_keywords:
  - storage cost
  - lifecycle policy
  - storage class
  - STANDARD_IA
  - ARCHIVE
  - tiering
  - retrieval cost
  - minimum storage duration
  - cost optimization
  - intelligent tiering
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# Lifecycle & Cost Analysis

Diagnose why storage costs are higher than expected, and recommend lifecycle strategies. Most cost surprises come from: minimum storage duration penalties (IA=30d, ARCHIVE=90d), small-file overhead (each file = 1 billable object), and retrieval fees on archived data.

## Decision Tree

```
Cost concern →
  ├─ "Why is my storage bill so high?" →
  │   ├─ Many small files (<64KB)? → Minimum billable size (IA=64KB, ARCHIVE=128KB)
  │   ├─ Objects in wrong tier? → IA objects accessed frequently → retrieval costs
  │   ├─ Previous versions accumulating? → Versioning costs (each version = separate billable object)
  │   └─ Incomplete multipart uploads? → Orphaned parts still billable
  ├─ "What lifecycle rules should I set?" →
  │   ├─ Know access pattern? → Hot→30d→IA→90d→ARCHIVE→180d→DEEP_ARCHIVE
  │   └─ Unknown access pattern? → Intelligent Tiering (auto-moves based on access)
  ├─ "Should I use IA or Intelligent Tiering?" →
  │   ├─ Predictable access pattern? → Manual lifecycle (cheaper)
  │   └─ Unpredictable access? → Intelligent Tiering (monitoring fee < retrieval mistakes)
  └─ No cost data at all? → Request: bucket inventory, total objects, size distribution, storage class breakdown
```

## Workflow

### Step 1: Inventory the Storage
Identify: total object count, total size, size distribution (P10/P50/P90), storage class per object, versioning status (each version = separate object). See `references/inventory-cost-analysis.md`.

### Step 2: Calculate Current Cost
Breakdown: storage cost (GB-month per class), request cost (PUT/GET/LIST), retrieval cost (IA/ARCHIVE), minimum duration penalties. See `references/storage-class.md` for per-provider pricing.

### Step 3: Identify Cost Amplification
- **Small files** under minimum billable size: each round UP to 64KB (IA) or 128KB (ARCHIVE). A 1KB file in IA costs 64KB.
- **Premature transitions**: IA has 30-day minimum, ARCHIVE has 90-day. Transitioning earlier = penalty for remaining days.
- **Retrieval costs**: ARCHIVE retrieval is expensive (per-GB + per-request). Bulk retrieval is cheapest.
- **Versioning**: Each version = full object cost. Noncurrent versions in IA still billable.
- **Incomplete multipart**: Orphaned parts billed at STANDARD rate until deleted.

### Step 4: Recommend Lifecycle Strategy
- **Hot data** (<30 days since last access): STANDARD
- **Warm data** (30-90 days): STANDARD_IA (or Intelligent Tiering)
- **Cold data** (90-180 days): ARCHIVE (or Glacier)
- **Frozen data** (>180 days): DEEP_ARCHIVE (or Glacier Deep Archive)
- Add rule to delete incomplete multipart uploads after 7 days

### Step 5: Estimate Savings
Monthly savings = current cost − projected cost after lifecycle. Include minimum duration risk in calculation.

## Output Format

```markdown
# Cost Analysis: [one-line]
**Monthly cost**: [current] → [projected] (save [amount]/month, [%])
**Confidence**: high | medium | low (depends on inventory completeness)

## Current State
- Objects: [count], Total: [size]
- Storage class distribution: [breakdown]
- Versioning: [enabled/disabled], Noncurrent: [count]

## Cost Amplification Found
1. **[issue]** — costs [amount]/month
2. ...

## Recommended Lifecycle
1. Rule: [transition STANDARD→IA after X days]
2. Rule: [transition IA→ARCHIVE after Y days]
3. Rule: [delete incomplete multipart after 7 days]
4. ...
```

## Examples

### Example 1: Small files in IA destroying savings
**Input**: 10M objects × 1KB in STANDARD_IA. Bill = much higher than expected.
**Diagnosis**: Minimum billable size = 64KB per IA object. 10M × 1KB files billed as 10M × 64KB = 640 GB billed, but only 10 GB stored. 64× cost amplification.
**Recommendation**: Archive small files into larger objects (tar/gz), or switch to STANDARD if frequently accessed.

### Example 2: Premature ARCHIVE transition
**Input**: Lifecycle rule moves objects to ARCHIVE after 30 days. Retrieval costs are 3× storage savings.
**Diagnosis**: ARCHIVE minimum duration = 90 days. Objects transitioned at 30d incur 60d penalty on retrieval. Plus retrieval cost is $0.01/GB for expedited.
**Recommendation**: Transition to IA at 30d, ARCHIVE at 90d. Bulk retrieval for archived objects.

### Example 3: Orphaned multipart parts
**Input**: Bill shows 500GB of storage but only 200GB of visible objects.
**Diagnosis**: 300GB of incomplete multipart upload parts, billed at STANDARD rate indefinitely.
**Recommendation**: Add lifecycle rule: `AbortIncompleteMultipartUpload` after 7 days. Immediate savings: 300GB/month.

## References
- `references/storage-class.md` — Per-class pricing (STANDARD, IA, ARCHIVE, DEEP_ARCHIVE)
- `references/lifecycle.md` — Lifecycle rule schema, transition constraints
- `references/inventory-cost-analysis.md` — How to get object inventory for cost analysis
- `references/request-cost.md` — PUT/GET/LIST/HEAD per-request pricing
- `references/provider-pricing.md` — Per-provider pricing differences (BOS/OSS/COS/AWS)
