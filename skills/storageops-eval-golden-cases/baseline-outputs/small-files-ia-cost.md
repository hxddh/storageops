# 摘要

Category: lifecycle_cost
Route: storageops-lifecycle-cost
Confidence: 0.85
Root Cause Type: small_object_cost

账单异常并非 provider 计费问题，而是 lifecycle 规则把大量 1 KB 小对象迁移到了
STANDARD_IA。Standard-IA 有 128 KB 的最小计费对象大小（minimum billable size），
每个 1 KB 对象都按 128 KB 计费，导致存储量被放大约 128 倍。

# 诊断结论

Root cause 是 small_object_cost：lifecycle 把小文件转入 STANDARD_IA，触发其
128 KB minimum 计费下限。这是一个成本反模式，存储数据量只有 10 GB，但 billable
存储量约为 1280 GB。

# 关键证据

- Lifecycle 规则 `MoveToIA-After30Days` 在 `logs/` 前缀上配置了 30 天后
  `Transition` 到 `STANDARD_IA`。
- STANDARD_IA 的 minimum billable object size 为 128 KB；每个 1 KB 对象按
  128 KB 计费（billable size 放大），1000 万个小对象 → 约 1280 GB。
- 这不是 provider 计费错误，而是存储类与对象大小不匹配的预期计费行为。

# 修复建议

- 修改 lifecycle 规则，用 object-size `filter`（最小对象大小阈值）排除 < 128 KB
  的小文件，使它们留在 Standard，不进入 IA。
- 或在迁移前 aggregate（聚合，例如打 tar 包）小文件，让单个对象超过 128 KB 再
  转 IA，从根本上避免最小计费放大。
- 重新评估按 cost 收益分层：仅对足够大、访问不频繁的对象做 IA transition。
