# 快速参考

## 安装（2 步）

```bash
pip install storageops
storageops install
```

## 配置 API Key

```bash
# 方式A：环境变量（推荐）
export DEEPSEEK_API_KEY=sk-xxx

# 方式B：本地文件（不受 shell 影响）
echo sk-xxx > ~/.storageops/agent/api-key
```

## 常用命令

```bash
# 诊断
storageops --print 's5cmd 429 错误'
storageops --print @debug.log '分析 rclone 日志'

# 交互模式
storageops

# 安装管理
storageops install --merge    # 合并到已有 Pi
storageops install --force    # 重装
storageops --version          # 版本 + 安装状态

# 会话管理（Pi 原生）
storageops -c                 # 恢复上次会话
storageops -r                 # 选择历史会话
```

## 诊断场景速查

| 错误码/现象 | 技能包 |
|------------|--------|
| 403 / AccessDenied | storageops-security-iam-policy |
| 429 / SlowDown | storageops-performance-diagnosis |
| SignatureDoesNotMatch | storageops-s3-protocol-compatibility |
| rclone/s5cmd 报错 | storageops-cli-sdk-diagnosis |
| DNS/TLS 不通 | storageops-network-endpoint-access |
| 成本/生命周期问题 | storageops-lifecycle-cost |
| CRR/版本管理 | storageops-replication-versioning |

## 目录结构

```
~/.storageops/                    ← 独立安装
├── agent/                        ← PI_CODING_AGENT_DIR
│   ├── settings.json
│   ├── api-key                   ← 可选，本地持久化 key
│   └── extensions/storageops.ts
└── skills/ (15个)

~/.pi/agent/                      ← 合并安装
├── settings.json                 ← 自动合并，原文件备份
├── extensions/storageops.ts
└── sessions/
```
