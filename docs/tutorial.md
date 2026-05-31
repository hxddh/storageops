# StorageOps Tutorial

## 5 分钟上手

### 第一步：连接到云主机

```bash
ssh -i ~/Documents/ssh/oracle/amd-1511/ssh-key-2026-04-11.key ubuntu@161.33.182.66
pi
```

### 第二步：描述你的问题

直接告诉 pi 你遇到的对象存储问题。不需要记住 skill 名字。例如：

| 你说 | pi 自动做的 |
|------|-----------|
| "rclone 报 corrupted on transfer" | 自动加载 `storageops-cli-sdk-diagnosis` → 对比 ETag → 路由到 `s3-protocol-compatibility` |
| "BOS 上传很慢，只有 10MB/s" | 自动加载 `storageops-triage` → 路由到 `performance-diagnosis` → BDP 分析 |
| "S3 返回 403 AccessDenied" | 自动加载 `security-iam-policy` → 策略评估 → 定位拒绝源 |
| "挂载的 BOS 上 git status 要 3 分钟" | 自动加载 `mount-filesystem-workspace` → 元数据放大估算 |

### 第三步：提供日志

pi 会告诉你需要什么证据以及如何获取。例如：

```bash
# pi 可能需要这些命令的输出
aws --version
rclone version
grep -i "error\|fail" rclone-debug.log | head -20
```

### 第四步：获得诊断报告

pi 会输出结构化诊断，包含：
- 根因分析
- 置信度评分
- 证据引用
- 修复建议（manual-only）
- 验证命令
- 降级推断（如果证据不足）

---

## 进阶使用

### 指定特定 Skill

```bash
# 在 pi 交互中
/skill:storageops-performance-diagnosis
```

### 使用诊断脚本

```bash
# 凭证安全加载
source scripts/credential-loader.sh bos

# rclone 配置审计
./scripts/rclone-config-auditor.sh

# 元数据放大估算
python3 scripts/metadata-amplification-estimator.py git-status 50

# 签名错误对比
python3 scripts/sigv4-error-diff.py error-response.xml

# 权限评估
python3 scripts/policy-permission-evaluator.py bucket-policy.json s3:GetObject "arn:aws:s3:::my-bucket/*"

# 复制状态检查
./scripts/replication-status-checker.sh source-bucket dest-bucket my-key

# Skill 健康检查
./scripts/skill-health-check.sh
```

---

## 常见问题 FAQ

### Q: 我该从哪里开始？
A: 直接告诉 pi 你的症状。它会自动路由到正确的诊断 Skill。如果 pi 不确定，会通过 `storageops-triage` 先分类。

### Q: 需要提供什么证据？
A: 越详细越好。至少提供：错误信息/状态码 + 使用的工具及版本 + endpoint/provider。pi 会告诉你还需要什么。

### Q: 为什么诊断置信度只有 0.5？
A: 证据不足。可能只提供了错误描述没有日志。pi 会告诉你需要补充什么来提升置信度。这不是失败——这是诚实的。

### Q: Skill 会修改我的 bucket 吗？
A: **不会。** 所有危险操作都标记为 `manual-only`，需要你手动确认。诊断完全是 read-only 的。

### Q: 支持哪些 Provider？
A: AWS S3（基线）、BOS（百度）、OSS（阿里）、COS（腾讯）、MinIO。每个都有 `provider-quirks` 参考文档。

### Q: 支持哪些工具？
A: rclone, awscli, s5cmd, bcecmd, obsutil, boto3/botocore, MinIO Client (mc), s3cmd。每个都有专用 reference。

### Q: 诊断出了错怎么办？
A: 检查 `limitations` — 诊断盲区已标注。补充证据后重新诊断。也可用 golden cases 做回归验证。

### Q: 能分析 BOS/OSS/COS 的 access log 吗？
A: 在 pi 中告诉它日志路径即可。对于 BOS access log，参考 `bos-log-analysis` skill 做更深度的分析。

### Q: 5 大绝对红线是什么？
A: 1) 禁止读取凭证文件 2) 禁止推荐公开访问 3) 禁止禁用TLS 4) 禁止自动写操作 5) 禁止编造证据
