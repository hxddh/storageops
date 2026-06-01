# StorageOps Quick Reference Card

## 一行速查 / One-Line Reference

| 症状 Keywords (中/英) | 一键诊断 Skill |
|-----------|---------------|
| `SignatureDoesNotMatch` / 签名不匹配 / ETag mismatch / ListObjects 异常 | `storageops-s3-protocol-compatibility` |
| `403` / `AccessDenied` / 权限拒绝 / IAM / bucket policy / KMS | `storageops-security-iam-policy` |
| `429` / `SlowDown` / 慢/超时/throughput低 / 上传下载慢 / 限流 | `storageops-performance-diagnosis` |
| rclone/s5cmd/awscli/boto3 报错 / debug log / corrupted on transfer / 传输损坏 | `storageops-cli-sdk-diagnosis` |
| mount 挂载慢 / git慢 / npm慢 / FUSE / 掉挂载 / workspace 卡 | `storageops-mount-filesystem-workspace` |
| 端点不通 / DNS失败 / TLS错误 / 专线 / VPC endpoint / 跨云 | `storageops-network-endpoint-access` |
| 存储费用高 / lifecycle 不生效 / 存储类选择 / 计费 / 成本 / 降本 | `storageops-lifecycle-cost` |
| 复制延迟/失败 / 版本冲突 / Object Lock / CRR / SRR / DeleteMarker | `storageops-replication-versioning` |
| 跨 provider 迁移 / 跨云迁移 / 数据搬迁 / BOS→OSS / 迁移估算 | `storageops-migration-sync` |
| CORS 报错 / 前端跨域 / preflight OPTIONS | `storageops-s3-protocol-compatibility` |
| 不确定属于哪个领域 / 帮我看看这个存储问题 | `storageops-triage` |
| 诊断完成, 要生成报告 / 写诊断报告 | `storageops-evidence-reporting` |
| 评估诊断质量 / 回归测试 | `storageops-eval-golden-cases` |

## 五大绝对红线

1. **禁止读取凭证文件** — 使用 `source scripts/credential-loader.sh`
2. **禁止推荐 `Allow */*`** — 违反最小权限原则
3. **禁止禁用 TLS 验证** — `--no-verify-ssl` 仅用于调试
4. **禁止自动执行写操作** — 所有 mutating 命令标记 `manual-only`
5. **禁止编造证据** — 所有结论必须有证据引用

## 三大诊断原则

1. **证据优先**: 无证据 = 推断 = 降置信度, 不是拒绝诊断
2. **降级不断**: 证据不足时不返回"N/A", 而是降级推断 + 标注盲区
3. **交叉验证**: 每个诊断结论列出排除假说, 防止单 domain 视野偏差

## 常用命令速览

```bash
# 启动交互式诊断会话
storageops
storageops "getting 429 SlowDown on uploads"   # 带初始问题启动
storageops @error.log                           # 带文件启动
aws s3 cp s3://bucket/key . 2>&1 | storageops  # 管道输入

# 离线快速分类（无需 Pi / API key）
storageops triage error.log
storageops triage error.log --format json

# 离线领域分析
storageops analyze security_iam_policy policy.json
storageops analyze cli_sdk_behavior rclone.log
storageops analyze performance_throughput s3-access.log

# 批量扫描多个文件
storageops scan logs/*.log

# 查看诊断历史
storageops memory list
storageops memory search "ETag mismatch"

# 回归评估（20 个黄金用例）
storageops eval --all

# HTTP API 服务
storageops serve                    # 启动 http://localhost:8080
storageops mcp                      # Claude Desktop MCP 服务器
```
