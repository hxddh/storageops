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
# 安全加载凭证
source scripts/credential-loader.sh [bos|aws|oss] [profile]

# rclone 配置审计
./scripts/rclone-config-auditor.sh

# 复制状态检查
./scripts/replication-status-checker.sh <src-bucket> <dst-bucket> <key>

# 签名错误对比
python3 scripts/sigv4-error-diff.py <error-response.xml>

# 元数据放大估算
python3 scripts/metadata-amplification-estimator.py git-status 50

# 权限评估
python3 scripts/policy-permission-evaluator.py <policy.json> <action> <resource>
```
