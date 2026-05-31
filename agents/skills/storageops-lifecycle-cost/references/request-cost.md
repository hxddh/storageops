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

## Cost Estimation Formulas

<!-- 口径声明：所有金额为估算。默认单价为参考值，请以实际 provider 账单为准。 -->

**默认参考单价 (估算用，单位: 元·GB⁻¹·月⁻¹):**

| Storage Class | 月度单价 (参考) | 最小计费时长 | 最小计费对象大小 |
|---|---|---|---|
| STANDARD | 0.12 | 无 | 无 |
| STANDARD_IA | 0.08 | 30 天 | 128 KB |
| ARCHIVE | 0.033 | 90 天 | 无 |
| COLD_ARCHIVE | 0.015 | 180 天 | 无 |

### 1. 月度存储费用估算

```
storage_cost = size_gb × unit_price

IA 小对象修正: effective_size_gb = max(actual_size, min_billable_size) per object
  min_billable_size = 128 KB for IA
```

### 2. 生命周期沉降降本估算

```
current_cost  = idle_size_gb × standard_price
ia_cost       = idle_size_gb × ia_price   (目标: STANDARD_IA)
archive_cost  = idle_size_gb × archive_price (目标: ARCHIVE)

monthly_savings_ia     = idle_size_gb × (standard_price - ia_price)
monthly_savings_archive = idle_size_gb × (standard_price - archive_price)

# 注意: 沉降操作本身产生请求费用
# transition_cost = object_count × transition_request_price / 1000
```

### 3. 最小存储时长惩罚估算

```
# IA: 30天最小时长, Object < 30天被删除 → 仍按30天计费
early_delete_penalty = early_deleted_size_gb × ia_price × (30 - actual_days) / 30

# 检查: 对象在 IA 中存了几天后被删除/迁回标准?
# 如有大量短期 IA 对象，此费用可能显著
```

### 4. 检索费用估算 (Archive)

```
# Archive 检索: 按检索速度和数据量计费
retrieval_cost = retrieval_size_gb × retrieval_price_per_gb

# 批量检索 (5-12小时) 比 加急检索 (1-5分钟) 便宜很多
```

### 5. 请求费用估算

```
put_cost  = put_count  / 1000 × put_price_per_1000
list_cost = list_count / 1000 × list_price_per_1000
get_cost  = get_count  / 1000 × get_price_per_1000

lifecycle_transition_cost = transitioned_count / 1000 × transition_price_per_1000
```

### 6. 生命周期请求成本

```
# 将 100 万对象沉降到 IA 的一次性请求成本:
transition_requests = 1,000,000 objects / 1000 × $0.01 = $10

# 如果后续这些对象被访问被迁回 Standard，双向请求成本翻倍
```

## 降级诊断规范

### 无 Lifecycle 配置
不要仅报告"无 lifecycle 配置"。基于对象年龄分布和访问模式推荐应创建的规则:
- 统计各前缀对象的最后访问时间分布
- 识别 7天/30天/90天 无访问的对象比例
- 推荐: 30天无访问 → 沉降 IA, 90天无访问 → 沉降 Archive
- 推荐: 配置 abort-incomplete-multipart-upload (如 7天)

### 无成本数据 (仅 lifecycle 规则审查)
即使没有实际账单数据，也应:
- 识别规则中的成本反模式 (如: 过早 transition 触发最短时长惩罚)
- 指出可能产生大量 transition 请求的规则 (大规模前缀匹配)
- 给出"若 N% 对象匹配此规则，预估月费范围为 X~Y"的区间估算

### 无对象大小分布数据
如果只有 lifecycle 配置文件、没有 inventory data:
- 分析规则覆盖的前缀和过滤条件
- 指出哪些规则可能因为小对象 (<128KB) 在 IA 中造成成本放大
- 建议用户获取 inventory report 以精确分析

### 数据窗口不足
cost/baseline/lifecycle 维度理想需 >=30 天数据:
- <7天窗口: 报告"因数据窗口不足，冷热分析为下限估计"
- <30天窗口: 30天闲置检测不可靠，标注数据窗口和置信度降低原因

## S3-Compatible Provider Differences

Request costs vary significantly between providers. Some charge for DELETE.
Some charge differently for LIST. Always check the specific provider's pricing page.
