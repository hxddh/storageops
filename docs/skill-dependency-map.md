# StorageOps Skill Dependency & Routing Map

## Primary Routing Flow

```
                    storageops-triage
                    (入口: 分类 + 证据评估 + 路由)
                    /      |      |     |     \
                   /       |      |     |      \
    s3-protocol  cli-sdk  perf   mount  network  security  lifecycle  replication  access-log
        |          |       |      |      |         |         |          |
        └──────────┴───────┴──────┴──────┴─────────┴─────────┴──────────┘
                                    |
                          storageops-evidence-reporting
                          (输出: 结构化诊断报告)
                                    |
                          storageops-eval-golden-cases
                          (质量门控: 回归验证)
```

## Cross-Domain Dependency Matrix

| Skill | 依赖 | 被依赖 |
|-------|------|--------|
| **triage** | (所有 — 入口) | 所有 specialist skills |
| **access-log-analysis** | provider log formats, anomaly thresholds, cost attribution | security (403 spikes), performance (503/SlowDown), lifecycle-cost |
| **s3-protocol-compatibility** | provider-quirks (BOS/OSS/COS/MinIO), sigv4.md, cors.md | cli-sdk, security, replication |
| **cli-sdk-diagnosis** | s3-protocol (ETag/sig errors), rclone.md, awscli.md, s5cmd.md, ... | (triage routes tool errors here) |
| **performance-diagnosis** | network (RTT baseline), throughput-model.md, throttling.md | mount (metadata amplification) |
| **mount-filesystem-workspace** | performance (metadata cost), fuse.md, posix-semantics.md | (standalone for mount issues) |
| **network-endpoint-access** | tls-mtu-rtt.md, private-access.md | performance (RTT), replication (CRR network) |
| **security-iam-policy** | s3-protocol (签名验证排除) | replication (cross-account), cost (KMS cost) |
| **lifecycle-cost** | request-cost.md (公式), storage-class.md | (standalone, 引用 security 排除权限) |
| **replication-versioning** | network (CRR latency), security (cross-account IAM) | (standalone) |
| **evidence-reporting** | reporting-best-practices.md | 所有 specialist skills (输出端) |
| **eval-golden-cases** | 所有 golden cases, eval-rubric.md, skill-taxonomy.json | 所有 skills (质量验证) |

## Routing Escalation Paths

```
问题未解决时, 按此路径升级:

1. triage 检查 → 路由到 specialist A
2. Specialist A 诊断 → 发现交叉域依赖 → 路由到 specialist B
3. Specialist B 验证 → 确认/排除
4. 回到 specialist A → 综合结论
5. evidence-reporting → 生成报告
6. eval-golden-cases → 质量检查 (可选)
```

## Common Cross-Skill Patterns

| 初始 Skill | 常见 Cross | 触发条件 |
|-----------|-----------|---------|
| cli-sdk-diagnosis | → s3-protocol-compatibility | ETag mismatch / SignatureDoesNotMatch in any tool |
| cli-sdk-diagnosis | → network-endpoint-access | Timeout in debug log |
| performance-diagnosis | → network-endpoint-access | High RTT / no network baseline |
| performance-diagnosis | → mount-filesystem-workspace | Slow stat/open on mount |
| security-iam-policy | → s3-protocol-compatibility | 403 with SignatureDoesNotMatch |
| replication-versioning | → network-endpoint-access | High replication lag |
| replication-versioning | → security-iam-policy | Cross-account KMS/permissions |
| lifecycle-cost | → performance-diagnosis | High request cost from metadata storms |
| mount-filesystem-workspace | → performance-diagnosis | Quantify metadata amplification |
| network-endpoint-access | → s3-protocol-compatibility | TLS error with provider-specific cert |
| access-log-analysis | → security-iam-policy | AccessDenied/403 spike tied to requester/policy |
| access-log-analysis | → performance-diagnosis | 503/SlowDown spike or hot-prefix pattern in logs |
| access-log-analysis | → lifecycle-cost | Request/cost attribution anomaly |
