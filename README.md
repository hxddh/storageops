# StorageOps

**S3 兼容对象存储 AI 诊断工具** — 一个 [Pi Coding Agent](https://github.com/earendil-works/pi-coding-agent) 的扩展包。

遇到 `AccessDenied`、`SlowDown`、`SignatureDoesNotMatch`、`corrupted on transfer` 之类的 S3 错误？直接把错误信息丢给 StorageOps，AI 帮你诊断根因。

```bash
pip install storageops    # 安装
storageops install         # 初始化
storageops 's5cmd sync 报 429 SlowDown'  # 诊断
```

## 为什么选 StorageOps

| | 传统排查 | StorageOps |
|---|---------|------------|
| 504/403/429 诊断 | Google → 论坛 → 工单 | 一个命令，30 秒出结果 |
| 跨服务商差异 | 逐个查文档 | 16 个技能包覆盖 AWS/BOS/OSS/COS/MinIO |
| 安全 | 手动脱敏 | `scan_secrets` 自动扫描 + 脱敏 |
| 安装 | 克隆仓库 + 8 步配置 | `pip install` + `storageops install` |

## 快速开始

### 1. 安装

```bash
pip install storageops
storageops install
```

> 如果你已经在用 Pi Coding Agent，安装时会检测到 `~/.pi/` 并询问是否合并。

### 2. 配置 API Key

```bash
# 方式A：环境变量
export DEEPSEEK_API_KEY=sk-xxx

# 方式B：本地文件（不受 shell 影响）
echo sk-xxx > ~/.storageops/agent/api-key
chmod 600 ~/.storageops/agent/api-key
```

### 3. 诊断

```bash
# 交互式（推荐）
storageops

# 单次诊断
storageops --print 's5cmd sync 报 429 SlowDown 错误，快速诊断'

# 分析日志文件
storageops --print @/path/to/rclone-debug.log '这个 rclone 日志分析一下'
```

### 4. 更新升级

```bash
pip install --upgrade storageops && storageops install --force
```

> 两条命令，无交互阻塞，CLI + 技能包一起更新。

## 支持的诊断场景

| 技能包 | 领域 |
|--------|------|
| `storageops-triage` | 入口分流 |
| `storageops-access-log-analysis` | 访问日志 / 错误尖峰 / 流量与成本归因 |
| `storageops-security-iam-policy` | 403 / KMS / Bucket Policy |
| `storageops-performance-diagnosis` | 429 / 限流 / 性能瓶颈 |
| `storageops-s3-protocol-compatibility` | SigV4 / CORS / 协议兼容 |
| `storageops-cli-sdk-diagnosis` | rclone / s5cmd / awscli / boto3 |
| `storageops-network-endpoint-access` | DNS / TLS / VPC Endpoint |
| `storageops-lifecycle-cost` | 生命周期 / 成本分析 |
| `storageops-replication-versioning` | CRR / SRR / DeleteMarker |
| `storageops-mount-filesystem-workspace` | s3fs / FUSE / 工作空间 |
| `storageops-migration-sync` | 数据迁移 / 同步 |
| `storageops-data-consistency` | ETag / Checksum |
| `storageops-bigdata-pipeline` | Spark / Hive / S3A |
| `storageops-event-notification` | SQS / Lambda 通知 |
| `storageops-evidence-reporting` | 诊断报告生成 |
| `storageops-eval-golden-cases` | 质量验证 |

## 内置工具

| 工具 | 用途 |
|------|------|
| `scan_secrets` | 扫描 + 脱敏 AK/SK/token 等凭据 |
| `detect_domain` | 签名识别错误类别（403/429/SigV4 等） |
| `search_memory` | 搜索历史 Session 中的诊断记录 |

## 安装详情

### 独立安装（默认）

```bash
storageops install
```
→ 安装到 `~/.storageops/`，不影响你已有的 Pi 配置。

### 合并安装

```bash
storageops install --merge
```
→ 安装到 `~/.pi/`，融入现有的 Pi 环境；extension 位于 `~/.pi/agent/extensions/`，skills 位于 `~/.pi/skills/`，并自动备份 `settings.json`。

### 强制重装

```bash
storageops install --force
```

## 架构

```
~/.storageops/agent/           ← Pi 配置目录 (PI_CODING_AGENT_DIR)
├── settings.json              ← skills + provider/model 配置
├── api-key                    ← 可选：持久化 API key
├── extensions/
│   └── storageops.ts          ← 3 inline TypeScript 工具
└── sessions/                  ← Pi 管理的诊断记录

~/.storageops/skills/           ← 16 个诊断技能包
├── storageops-triage/
├── storageops-security-iam-policy/
└── ...
```

- **零 Python agent 代码** — agent loop / session / tool dispatch 由 Pi 原生处理
- **零子进程** — 工具在 Pi TypeScript 运行时内联执行
- **两行安装** — `pip install` + `storageops install`
- **API key 持久化** — 写入 `~/.storageops/agent/api-key`，不受 shell 启动文件影响

## 开发

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
pip install -e .
storageops install
```

贡献方式：修改 `skills/` 下的 SKILL.md 或 `storageops_cli/extensions/storageops.ts`，提交 PR。Skill 质量规范见 `docs/skill-quality-guide.md`；分类与 golden case 路由契约见 `docs/skill-taxonomy.md`。

## License

MIT
