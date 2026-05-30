# Request Cost Analysis

## S3 Request Types and Costs

| Request Type | Cost (AWS, per 1000) | When Charged |
|---|---|---|
| PUT, COPY, POST, LIST | $0.005 | Object upload, copy, list |
| GET, SELECT, all others | $0.0004 | Object download, HEAD, etc. |
| DELETE, CANCEL | Free | Object deletion |
| Lifecycle Transition | $0.01 (per 1000) | Objects transitioned by lifecycle |

## When Request Costs Matter

### High Request Volume, Small Objects
- 1 million PUT requests × $0.005/1000 = $5.00 (negligible).
- 1 billion PUT requests × $0.005/1000 = $5,000 (significant).

### Frequent LIST Operations
- Each LIST request costs (part of PUT/COPY/POST/LIST tier).
- Listing a bucket with millions of objects may require thousands of paginated LIST requests.
- Each page = 1 request = billable.

### Lifecycle Transition Request Costs
- Transitioning objects via lifecycle generates PUT requests.
- 100 million objects × $0.005/1000 = $500.
- Plus lifecycle transition charge: 100 million × $0.01/1000 = $1,000.
- Total: $1,500 for a one-time transition of 100M objects.

### HEAD Object Costs
- HEAD is in the GET tier ($0.0004/1000).
- Mount-based workspaces generate massive HEAD requests (stat → HeadObject).
- 100 million HEAD requests × $0.0004/1000 = $40 (negligible per request, but scales).

## Small Object Cost Amplification

### Scenario: 1 Billion Small Objects (1 KB each)

**Storage cost:**
- 1B × 1 KB = 1 TB in Standard: ~$23/month (varies by region).

**Request cost (if uploaded once):**
- 1B PUT requests × $0.005/1000 = **$5,000** (one-time).

**If in Standard-IA (minimum billable size 128KB):**
- 1B × 128 KB = 128 TB equivalent: ~$1,600/month.
- Storage cost is 70× higher than the actual data volume!

**Lesson:** Small objects can make request costs and minimum billable size dominate
total cost, especially in infrequent-access tiers.

## Cost Attribution per Prefix

To attribute request costs:
1. Enable S3 server access logging or use CloudTrail data events.
2. Parse access logs to count requests by operation type per prefix.
3. Multiply by the per-request cost.
4. This is manual in v0.1; automation planned for storageops-core.

## Request Cost Reduction Strategies

1. **Batch operations:** DeleteObjects (up to 1000 per request) instead of individual DELETEs.
2. **Aggregate small files:** TAR or ZIP small files before upload.
3. **Reduce LIST operations:** Use prefix organization to reduce pagination.
4. **Use lifecycle rules:** Instead of manually deleting old objects, use expiration rules (lower per-object cost).
5. **Avoid unnecessary HEAD requests:** Cache object metadata locally.
6. **S3 Inventory:** Use S3 Inventory (billable) instead of repeated LIST operations for metadata.

## S3-Compatible Provider Differences

Request costs vary significantly between providers. Some charge for DELETE.
Some charge differently for LIST. Always check the specific provider's pricing page.
