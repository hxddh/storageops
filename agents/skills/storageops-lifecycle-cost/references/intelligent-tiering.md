# Intelligent Tiering

## What It Does

S3 Intelligent-Tiering automatically moves objects between two (or three) access tiers
based on access patterns:
- **Frequent Access Tier:** Same price as S3 Standard.
- **Infrequent Access Tier:** Same price as S3 Standard-IA.
- **Archive Instant Access Tier (optional):** Same price as S3 Glacier Instant Retrieval.
- **Archive Access Tier (optional):** Same price as S3 Glacier Flexible Retrieval.
- **Deep Archive Access Tier (optional):** Same price as S3 Glacier Deep Archive.

No retrieval charges. No minimum duration charges for tier changes.

## Costs

### Monitoring and Automation Fee
- Per-object monthly fee (e.g., $0.0025 per 1000 objects).
- Applied to ALL objects in Intelligent-Tiering, regardless of access pattern.
- This is the key factor in the cost equation.

### Storage Cost
- Same as the active tier (Frequent, Infrequent, Archive, etc.).
- No transition charges between tiers (automated).

## When Intelligent-Tiering Makes Sense

### YES:
- Access pattern is truly unpredictable.
- Object count is manageable (monitoring fee per object).
- Average object size is reasonably large (monitoring fee is fixed per object).
- Lifecycle rules are complex or hard to maintain manually.

### NO:
- Access pattern is well-known (e.g., daily access for 7 days, then never).
- Object count is extremely high (billions) — monitoring fee dominates.
- Objects are very small — monitoring fee per object exceeds storage cost.
- You can model access patterns with simple lifecycle rules.

## Break-Even Calculation

For a given object:
```
MonitoringFeePerMonth = MonitoringFeeRate × 1 object

ManualApproachCost = (StorageForFrequentPeriod × FrequentPrice) +
                     (StorageForInfrequentPeriod × InfrequentPrice) +
                     (TransitionRequestCost)

IntelligentTieringCost = (StorageForFrequentPeriod × FrequentPrice) +
                         (StorageForInfrequentPeriod × InfrequentPrice) +
                         (MonitoringFeePerMonth)
```

Intelligent-Tiering wins when the monitoring fee is less than the overhead of
manual lifecycle management (including the risk of manual misconfiguration).

## Intelligent Tiering on S3-Compatible Providers

Most S3-compatible providers do NOT offer Intelligent-Tiering. As of 2024:
- **AWS S3:** Supported, with optional archive tiers.
- **Tencent COS:** Limited support.
- **BOS, OSS, OBS, MinIO:** Not supported.

For providers without Intelligent-Tiering, lifecycle rules must be configured manually.
