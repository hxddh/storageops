# Storage Class Comparison

## AWS S3 Storage Classes

| Class | Minimum Duration | Retrieval Cost | Retrieval Time | Use Case |
|---|---|---|---|---|
| S3 Standard | None | None | Milliseconds | Frequent access |
| S3 Intelligent-Tiering | None (monitoring fee) | None | Milliseconds | Unpredictable access |
| S3 Standard-IA | 30 days | Per GB | Milliseconds | Infrequent access |
| S3 One Zone-IA | 30 days | Per GB | Milliseconds | Non-critical, infrequent |
| S3 Glacier Instant Retrieval | 90 days | Per GB | Milliseconds | Archive, instant access |
| S3 Glacier Flexible Retrieval | 90 days | Per GB | Minutes to hours | Archive, rare access |
| S3 Glacier Deep Archive | 180 days | Per GB | 12-48 hours | Long-term archive |
| S3 Express One Zone | None | None | Microseconds | High-performance |

## Key Cost Concepts

### Minimum Storage Duration
- If object is deleted or transitioned before the minimum duration, you are charged for the full minimum duration.
- Example: Object moved to Standard-IA, then deleted after 10 days → charged for 30 days of Standard-IA.
- This applies to ALL storage classes except Standard and Express One Zone.

### Minimum Billable Object Size (Standard-IA, One Zone-IA)
- Objects < 128 KB are billed as 128 KB.
- Example: 10,000 objects of 1 KB each in Standard-IA = billed as 10,000 × 128 KB = 1.28 GB, not 10 MB.
- This makes Standard-IA expensive for small objects.

### Retrieval Cost
- **Standard-IA, One Zone-IA:** Charged per GB retrieved.
- **Glacier classes:** Charged per GB retrieved, with higher rates.
- **Bulk retrieval (Glacier):** Cheaper but slower (5-12 hours).
- **Expedited retrieval (Glacier):** Fast (1-5 minutes) but expensive.

### Data Retrieval Charges After Transition
- Transitioning objects from Standard to Standard-IA does NOT incur retrieval charges.
- Retrieving Standard-IA objects DOES incur retrieval charges.
- Frequent reads of Standard-IA objects can cost more than Standard.

### Monitoring and Automation Charges (Intelligent-Tiering)
- Per-object monthly fee for monitoring access patterns.
- Worth it for unpredictable workloads but not for predictable ones.

## Storage Class Selection Decision Tree

### Q1: Is the data accessed frequently?
- **YES (multiple times per hour/day):** S3 Standard or Express One Zone.
- **NO (once a week or less):** Consider lower-cost tiers.

### Q2: Can the data be recreated?
- **YES:** One Zone-IA (cheaper, not resilient to AZ loss).
- **NO:** Standard-IA (multi-AZ).

### Q3: If accessed rarely, how fast does retrieval need to be?
- **Milliseconds:** Standard-IA, Intelligent-Tiering.
- **Minutes to hours:** Glacier Flexible Retrieval.
- **12-48 hours:** Glacier Deep Archive.

### Q4: Is the access pattern unpredictable?
- **YES:** Consider Intelligent-Tiering.
- **NO:** Choose the appropriate static class.

### Q5: What is the average object size?
- **< 128 KB:** Avoid Standard-IA (minimum billable size penalty).
- **128 KB–1 MB:** Standard-IA acceptable but monitor.
- **> 1 MB:** Standard-IA cost-effective for infrequent access.

## S3-Compatible Provider Equivalents

| AWS | Alibaba OSS | Huawei OBS | Baidu BOS | Tencent COS |
|---|---|---|---|---|
| Standard | Standard | Standard | Standard | Standard |
| Standard-IA | IA | Warm | Standard-IA | Standard-IA |
| One Zone-IA | - | - | - | One Zone-IA |
| Glacier | Archive | Cold | Archive | Archive |
| Deep Archive | Cold Archive | Deep Archive | Cold | Deep Archive |
| Intelligent-Tiering | (not supported) | (not supported) | (not supported) | Intelligent Tiering |

Note: Provider storage classes evolve. This table may not be exhaustive. Always
check the provider's current documentation.
