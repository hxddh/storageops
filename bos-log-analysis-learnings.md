# bos-log-analysis vs StorageOps — 可借鉴思路分析

> `bos-log-analysis` 是一个深度单一（BOS access log），`StorageOps` 是广度覆盖（11 个诊断域）。
> 两者不是竞争关系，而是互补。但 bos-log-analysis 在深度执行层面积累了大量可迁移的模式。

---

## 一、核心差异

| 维度 | bos-log-analysis | StorageOps |
|------|-----------------|------------|
| 定位 | **可执行的诊断产品** | **诊断知识框架** |
| 深度 | 单域极深（14 个分析维度 + 28 条 SQL） | 11 个域广覆盖，各域深度不一 |
| 脚本 | `load_creds.sh`, `convert_csv_to_parquet.py`, `setup_duckdb.sql` | 全部 `scripts/README.md` 空壳 |
| 输出 | 格式化中文报告模板，含量化预测（¥） | YAML + Markdown 结构，但缺少具体输出模板实例 |
| 凭证安全 | 4 级优先级树 + 绝对红线 + 不回显 | 仅"redact secrets"原则声明 |

---

## 二、StorageOps 应借鉴的具体模式

### 1. 凭证安全协议（最高优先级）

**bos-log-analysis 做了什么：**
- `load_creds.sh` 实现 4 级凭证获取优先级树（环境变量 → `~/.aws/credentials` awk 解析 → `~/.bce/credentials` → 交互 `read -s`）
- 两条绝对红线：禁止命令行明文 AK/SK、禁止以任何方式读取/查看凭证文件内容
- 正确做法是"根本不去看凭证文件，直接 `source scripts/load_creds.sh`"
- 分析结束后主动提醒 `unset` 环境变量

**StorageOps 现状：**
- 所有 skill 仅说 "Redact AK/SK/token/cookie/Authorization as `[REDACTED]`"
- 没有凭证获取机制，没有安全红线详细说明

**建议借鉴：**
- 创建 `scripts/credential-loader.sh` 通用凭证加载脚本
- 在每个涉及凭证的 skill 的 Safety rules 中增加"禁止 `cat`/`read` 凭证文件"的绝对红线
- 在 CLI/SDK diagnosis skill 中增加"分析结束后提醒清理本地凭证残留"

### 2. SQL/查询模板库（中优先级）

**bos-log-analysis 做了什么：**
- `references/common_queries.sql` — 28 条可复用的参数化 SQL，覆盖概览、错误码分布、流量时序、热点 IP、慢请求、行为链分析、容量回归、成本预测
- 每条查询有注释说明用途和适用场景
- 所有查询引用统一的 `bos_logs` 视图

**StorageOps 现状：**
- 所有技能只有诊断 workflow 文本描述，没有可执行的查询模板
- Performance skill 提到测量方法但没给具体命令

**建议借鉴：**
- 为 `storageops-performance-diagnosis` 创建 `references/performance_queries.sql` — 如抖动分析、P50/P90/P99 时延分布、429 时间序列
- 为 `storageops-security-iam-policy` 创建 `references/policy_checklist.sql` — 如桶策略评估步骤
- 为 `storageops-data-consistency` 创建 `references/replication_audit.sql` — 对象状态对比查询
- 统一约定：所有查询模板引用同一个标准化的 evidence 结构

### 3. 量化预测能力（高优先级）

**bos-log-analysis 做了什么：**
- Query 23: 线性回归预测 30 天存储容量和月度费用：`regr_slope()`, `regr_intercept()`, 产出 `daily_increase_mb_slope`, `predicted_capacity_gb_30d`, `predicted_monthly_cost_cny_30d`
- Query 24: 闲置对象检测 + 生命周期降本测算，直接给出 `current_standard_cost_cny`, `potential_ia_cost_cny`, `max_monthly_savings_cny`
- Query 19: CDN 降本潜力评估（区分 client_cache_redundant 和 cdn_redundant）
- 所有金额预测附带"口径声明"（单价假设、盲区警告）

**StorageOps 现状：**
- `storageops-lifecycle-cost` 只有结构性分析（"lifecycle rule 有问题"），没有成本估算公式
- 没有提供任何价格数据或计算模板

**建议借鉴：**
- 在 `storageops-lifecycle-cost/references/request-cost.md` 中加入成本估算公式
- 新增 `references/cost_estimation.sql` 模板（用户替换价格参数）
- 每个成本预测附带口径声明（如"以实际账单为准"、"存在统计盲区"）

### 4. 降级诊断 / 边界情况处理（高优先级）

**bos-log-analysis 做了什么：**
- 专门的"降级诊断规范" section，处理 4 种边缘案例：
  - **零流量异常** — 对比相邻周期、下钻根因
  - **无 GetObject 读流量** — 仍做冷数据审计、计算降本空间
  - **全是 GetBucket 列举** — 审计 API 利用率、分页逻辑
  - **缺失 Referer 信息** — 评估防盗链安全风险
- 每个边缘案例都有具体的降级分析路径，而不是简单返回"N/A"

**StorageOps 现状：**
- 假设有充分证据；当证据不足时只返回 `evidence_quality: insufficient`，不做降级推断
- 没有处理"零流量""全是元数据操作""缺失关键字段"的规范

**建议借鉴：**
- 在每个 skill 的 workflow 末尾增加"降级诊断"step
- 例如 performance skill：零流量 → 检查配置是否正确、客户端是否可达
- 例如 lifecycle-cost skill：无 lifecycle 配置 → 基于对象年龄分布推荐应创建的规则
- 例如 security skill：无 policy 文档 → 基于错误模式推断最可能的拒绝原因

### 5. "在途并发" vs "秒级 QPS" 区分

**bos-log-analysis 做了什么：**
- Query 17: 秒级 QPS 峰值
- Query 17b: **真实在途并发** (in-flight concurrency) — 用扫描线法（+1/-1 事件按时间累加），区分"每秒请求数"和"同时在途请求数"
- 解释："在途并发才是连接池压力" vs "每秒请求数是速率"

**StorageOps 现状：**
- Performance skill 只笼统提到"concurrency"，没有区分 QPS 和 in-flight concurrency
- Multipart tuning 部分说到"concurrency 控制并发请求"但没有解释不同概念的差异

**建议借鉴：**
- 在 `references/throughput-model.md` 或 `references/throttling.md` 中增加 "QPS vs in-flight concurrency" 概念说明
- 提供扫描线法计算 in-flight concurrency 的 SQL 模板

### 6. 数据盲区显式声明

**bos-log-analysis 做了什么：**
- 多个 query 附带"口径声明"块：
  - query 23: "回归仅基于日志窗口内增量，不含日志开始前存量"
  - query 24: "从未读取过的对象不在日志中，而这恰是最该沉降的冷数据"
  - query 27: "窗口外的历史残留需结合 ListMultipartUploads 核对"

**StorageOps 现状：**
- 没有 explicit "此诊断存在以下盲区" 的惯例
- `confidence` 字段暗示不确定性，但没有说明不确定性的具体来源

**建议借鉴：**
- 在每个 skill 的 output requirements 中增加 **`limitations`** 字段
- 示例：performance skill — "此诊断基于单时刻采样，未反映时间趋势"
- 示例：security skill — "未包含完整 IAM policy 文档，策略评估可能存在遗漏条件键"

### 7. 字段单位探测

**bos-log-analysis 做了什么：**
- `total_time` 字段单位（秒 or 毫秒）在执行分析前探测：跑 P50 看量级
- 探测结果影响归一系数 TT_FACTOR（1000 or 1）
- 结论在报告中标注采用单位

**StorageOps 现状：**
- 假设所有工具输出的字段含义已知，没有运行时探测步骤

**建议借鉴：**
- 在 CLI/SDK diagnosis skill 的 parse phase 增加"字段单位验证"步骤
- 例如 rclone 日志中 `chunk_size` 可能是 bytes 或 MiB，需要以实际值为准

### 8. 输出模板包含量化项

**bos-log-analysis 输出模板包含：**
- 日志解析成功率（不静默丢行）
- P50/P90/P99 时延分位数（不只是平均值）
- 95 分位带宽（因为运营商按月 95 峰值计费）
- 回归预测（未来 30 天容量和费用）
- 具体金额估算（元/月）
- 写后不读对象识别和归档降本测算
- 未完成分片成本黑洞估算
- 公网/内网流量分流（帮助区分计费流量）

**StorageOps 输出模板包含：**
- category, confidence, severity 等分类项
- 证据表、根因排序、验证命令
- 但缺少任何量化预测

**建议借鉴：**
- 在 `storageops-evidence-reporting` 的诊断报告模板中增加"量化影响评估"section
- 至少包含：影响范围（对象数/流量）、预估时间恢复、等效成本（如果适用）

---

## 三、不应借鉴的部分

| 模式 | 原因 |
|------|------|
| bos-log-analysis 深度绑定 BOS/DuckDB | StorageOps 是多 provider 通用框架，不应绑定特定工具 |
| bos-log-analysis 的 full-pipeline 自动化 | StorageOps 定位是诊断知识框架，不需要端到端自动化 |
| 过度量化的成本数字 | StorageOps 多数诊断域不涉及成本，保持工具中立性更好 |

---

## 四、优先落地建议

| 优先级 | 借鉴内容 | 落地文件 |
|--------|---------|---------|
| **P0** | 凭证安全协议 → 通用 credential-loader.sh | 新建 `scripts/credential-loader.sh`，所有涉及凭证的 skill 引用 |
| **P0** | 降级诊断规范 → 每个 skill 增加 edge case 处理 | 各 SKILL.md 的 workflow 末尾 |
| **P1** | 量化预测 → lifecycle-cost skill 增加公式和价格模板 | `lifecycle-cost/references/request-cost.md` |
| **P1** | 数据盲区声明 → output requirements 增加 `limitations` 字段 | 各 SKILL.md 的 output requirements |
| **P1** | 在途并发 vs QPS 区分 → throughput-model.md | `performance-diagnosis/references/throughput-model.md` |
| **P2** | SQL 查询模板库 | 各相关 skill 的 references/ |
| **P2** | 输出模板量化项 | `evidence-reporting/templates/` |

---

**总结**：bos-log-analysis 最大的启示不是它的 BOS 专业知识，而是它的**工程化深度**——从凭证安全到边缘降级，从量化预测到盲区声明，每一步都有具体机制支撑而非原则表述。StorageOps 在此基础上应补齐这些工程化层，从"诊断知识框架"升级为"可落地执行的诊断系统"。
