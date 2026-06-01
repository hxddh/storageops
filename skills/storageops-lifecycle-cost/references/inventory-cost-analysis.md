# Inventory-Based Cost Analysis

## Why Inventory-Based Analysis

S3 Inventory provides a scheduled CSV/ORC/Parquet report of all objects in a bucket,
including:
- Key (object path).
- Size.
- LastModified date.
- Storage class.
- ETag.
- Replication status.
- Encryption status.
- Intelligent-Tiering access tier.

This is the foundation for prefix-level cost attribution.

## Cost Attribution Model

### Storage Cost per Prefix
```
StorageCost(prefix) = Sum(ObjectSize(prefix, class) × StoragePrice(class))
```

### Request Cost per Prefix (Estimated)
Without access logs, estimate request cost based on:
- PUT cost: Number of objects × PUTRequestPrice (uploaded once).
- Or use LastModified distribution to estimate upload frequency.
- GET/LIST costs require access logs for accuracy.

### Minimum Duration Penalty per Prefix
```
For each object in IA/Archive that was deleted < minimumDuration:
    Penalty += ObjectSize × StoragePrice(class) × (minimumDuration - actualDuration)
```
Requires object creation date and deletion date data (not available in inventory alone).

### Minimum Billable Size Penalty per Prefix (IA classes)
```
For each object in IA with size < 128KB:
    Penalty += (128KB - ObjectSize) × IAPrice
```

## Cost Analysis Table Structure

| Prefix | Object Count | Total Size | Storage Class | Monthly Storage Cost | Min Size Penalty | Notes |
|---|---|---|---|---|---|---|
| logs/2024/ | 10,000 | 500 MB | STANDARD | $11.50 | $0 | Daily access |
| logs/2023/ | 100,000 | 5 GB | STANDARD_IA | $62.50 | $0 | Rarely accessed |
| images/ | 1,000,000 | 50 TB | STANDARD | $1,150 | $0 | High-traffic CDN origin |
| temp/small/ | 50,000,000 | 5 GB | STANDARD_IA | $640 | $12,000 | 50M objects < 128KB → huge penalty |

## Inventory Command (manual-only)

```bash
# Configure S3 Inventory (manual-only)
# manual-only: aws s3api put-bucket-inventory-configuration --bucket <bucket> --id <inventory-id> --inventory-configuration file://inventory.json

# List existing inventory configurations
# manual-only: aws s3api list-bucket-inventory-configurations --bucket <bucket>

# Get inventory report (download from the destination bucket)
# manual-only: aws s3 cp s3://<destination-bucket>/<prefix>/<report-key> .
```

## Analysis Steps

1. **Collect inventory report** (CSV/Parquet).
2. **Parse and group by prefix.**
3. **Compute per-prefix storage cost.**
4. **Identify top cost contributors.**
5. **Check for minimum billable size violations.**
6. **Flag objects approaching minimum duration thresholds.**
7. **Recommend lifecycle changes per prefix.**

## v0.1 Limitations

- Cost rates are illustrative (not real-time pricing).
- Minimum duration penalty requires additional data (deletion timestamps).
- Request cost requires access logs (not covered in v0.1 inventory analysis).
- Provider-specific pricing must be sourced by the user.
