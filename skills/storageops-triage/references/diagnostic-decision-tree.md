# StorageOps Diagnostic Decision Tree

## How to Navigate This Tree

Start at the top and follow the symptom path. Each node routes to the
appropriate specialist skill or requests more evidence.

```
用户报告对象存储问题
  │
  ├── 有明确错误码?
  │   ├── 403 AccessDenied
  │   │   ├── 含 SignatureDoesNotMatch?
  │   │   │   ├── YES → storageops-s3-protocol-compatibility (签名问题)
  │   │   │   │         同时检查 storageops-security-iam-policy (排除权限)
  │   │   │   └── NO  → storageops-security-iam-policy (权限问题)
  │   │   │             检查: IAM policy, Bucket policy, ACL, KMS, Block Public Access
  │   │   └── 仅特定 Object? → 可能是 Object ACL 或 KMS key policy
  │   │
  │   ├── 429 SlowDown / RequestRateLimitExceeded
  │   │   ├── 集中在特定 prefix? → storageops-performance-diagnosis (热点前缀)
  │   │   ├── 跨所有 prefix?     → storageops-performance-diagnosis (全局限流)
  │   │   └── 仅在特定工具出现?   → storageops-cli-sdk-diagnosis (工具并发配置)
  │   │
  │   ├── 5xx (500/502/503)
  │   │   ├── 偶发, 非限流 → storageops-network-endpoint-access (网络波动?)
  │   │   │                  + storageops-performance-diagnosis (服务端过载?)
  │   │   └── 持续 → 可能为 Provider 侧问题, 建议联系 Provider support
  │   │
  │   ├── 404 NoSuchKey / NoSuchBucket
  │   │   ├── 对象确实应该存在? → storageops-data-consistency (复制/版本问题)
  │   │   │   └── Versioning enabled? → storageops-replication-versioning
  │   │   └── 路径拼接问题? → storageops-cli-sdk-diagnosis (endpoint/prefix)
  │   │
  │   └── TLS/Certificate Error
  │       └── storageops-network-endpoint-access (证书过期/自签名)
  │
  ├── 性能问题? (慢, 超时)
  │   ├── Mount 相关? (s3fs, rclone mount, ossfs...)
  │   │   └── storageops-mount-filesystem-workspace
  │   ├── 特定工具慢但其他工具正常?
  │   │   └── storageops-cli-sdk-diagnosis (工具配置问题)
  │   ├── 跨 region / cross-cloud?
  │   │   ├── storageops-network-endpoint-access (先检查网络)
  │   │   └── storageops-performance-diagnosis (再调优)
  │   └── 同一 region 内慢?
  │       ├── storageops-performance-diagnosis (BDP/并发/限流分析)
  │       └── 若大量小文件 → 强调 small-file optimization
  │
  ├── 数据问题?
  │   ├── 对象在 replica 缺失/过期?
  │   │   └── storageops-replication-versioning (CRR/SRR)
  │   ├── delete 后对象还在/不在?
  │   │   └── storageops-replication-versioning (versioning/delete marker)
  │   ├── Event notification 未触发?
  │   │   └── storageops-replication-versioning (事件通知配置)
  │   └── Read-after-write 返回旧数据?
  │       └── storageops-s3-protocol-compatibility (provider consistency model)
  │
  ├── 成本问题?
  │   └── storageops-lifecycle-cost
  │       ├── 存储费高? → 检查 storage class / 最小计费时长
  │       ├── 请求费高? → 检查 small files / LIST 频率
  │       └── 流量费高? → 检查公网下行 / CDN
  │
  ├── 工具/SDK 错误?
  │   └── storageops-cli-sdk-diagnosis
  │       ├── rclone corrupted on transfer → ETag mismatch (引用 s3-protocol)
  │       ├── s5cmd concurrency 问题 → 参数调优
  │       └── awscli debug log → 解析签名/端点/重试
  │
  └── 无明确错误, 只有描述?
      └── storageops-triage (分类 + 证据缺口分析 + 路由)
          └── 使用 temporal pattern analysis 检测时间模式
```

## Evidence-Availability Shortcuts

| 你有... | 可以直接跳到... |
|----------|----------------|
| rclone debug log | storageops-cli-sdk-diagnosis |
| awscli --debug output | storageops-cli-sdk-diagnosis |
| 403 XML response | storageops-security-iam-policy |
| SignatureDoesNotMatch XML | storageops-s3-protocol-compatibility |
| mount hang / dmesg | storageops-mount-filesystem-workspace |
| DNS dig/traceroute | storageops-network-endpoint-access |
| cost report / lifecycle XML | storageops-lifecycle-cost |
| replication status FAILED | storageops-replication-versioning |
| 前端 CORS error | storageops-s3-protocol-compatibility (cors.md) |
| TLS cert expired | storageops-network-endpoint-access |

## Multi-Domain Patterns

Some issues require multiple skills. Common combinations:

| Symptom | Primary | Secondary | Why |
|---------|---------|-----------|-----|
| rclone corrupted on transfer | cli-sdk-diagnosis | s3-protocol-compatibility | ETag format is protocol issue |
| Slow upload (cross-region) | performance-diagnosis | network-endpoint-access | RTT determines BDP |
| 403 + SignatureDoesNotMatch | s3-protocol-compatibility | security-iam-policy | Could be auth OR policy |
| mount slow to start | mount-filesystem-workspace | performance-diagnosis | Metadata amplification + throughput |
| Replication lag | replication-versioning | network-endpoint-access | CRR depends on cross-region network |
