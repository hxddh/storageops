# Cost Attribution Guide — Access Log Analysis

Use access log data to attribute cloud storage costs to specific requesters, operations, and time windows.

## Request Pricing by Operation

### AWS S3 (us-east-1, per 1,000 requests)
| Operation | Cost/1k | Cost Ratio |
|-----------|---------|-----------|
| PUT, COPY, POST, LIST | $0.005 | 12.5x |
| GET, SELECT, Glacier Restore | $0.0004 | 1x (baseline) |
| DELETE, CANCEL | $0.0000 | Free |
| Lifecycle Transition | $0.01 | 25x |

### BOS (per 10,000 requests)
| Operation | Cost/10k |
|-----------|----------|
| PUT, POST, LIST | ¥0.01 |
| GET | ¥0.01 (usually same) |
| DELETE | Free |

### OSS (per 10,000 requests)
| Operation | Cost/10k |
|-----------|----------|
| PUT, POST | ¥0.01 |
| GET, HEAD | ¥0.01 |
| DELETE | Free |

### COS (per 10,000 requests)
| Operation | Cost/10k |
|-----------|----------|
| PUT, POST, LIST | ¥0.01 |
| GET, HEAD | ¥0.01 |
| DELETE | Free |

## Data Transfer Cost Attribution

**Internet Egress**: $0.09/GB (S3, first 10TB). Use `BytesSent` field sum.
**CloudFront Egress**: $0.02/GB (cheaper than direct S3 egress).
**Same-Region Transfer**: Usually free (between S3 and EC2 in same region).
**Cross-Region Transfer**: Charged at source region rates.

## Attribution Formula

```
Total cost = SUM(PUT_requests)  × PUT_price
           + SUM(GET_requests)  × GET_price
           + SUM(LIST_requests) × LIST_price
           + SUM(BytesSent)     × egress_price_per_byte
           + storage_cost       (from billing, not access logs)
```

## Cost Optimization Signals in Access Logs

| Pattern | Signal | Action |
|---------|--------|--------|
| >80% GET requests | Read-heavy workload | Add CloudFront CDN |
| Many small PUT requests | PUT amplification | Batch writes, buffer in application |
| LIST without GET | Inventory scanning | Use S3 Inventory, disable unnecessary scans |
| Many 404 errors | Wasted requests | Fix client code, use S3 Inventory |
| Cross-region requests | Cross-region data transfer | Route to same-region endpoint |
| BytesSent >> ObjectSize | Range GETs | Use CloudFront for partial downloads |
