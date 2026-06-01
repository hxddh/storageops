# 快速上手

2 分钟上手 StorageOps。

## 1. 安装

```bash
pip install storageops
storageops install
```

> **前提**：机器上需有 Node.js ≥ 20，用于运行 Pi Coding Agent。
> 如果没有：`curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs`

## 2. 配置 API Key

任选一种方式：

```bash
# 方式A：环境变量（推荐）
export DEEPSEEK_API_KEY=sk-xxx
export ANTHROPIC_API_KEY=sk-xxx

# 方式B：本地文件（不受 shell 影响）
echo sk-xxx > ~/.storageops/agent/api-key

# 方式C：Pi 内登录
storageops  → /login
```

## 3. 第一次诊断

```bash
# 交互模式
storageops

# 单次诊断
storageops --print 's5cmd sync 报了大量 429 SlowDown，帮我分析原因'
```

## 4. 保持更新

```bash
storageops update
```

> 此命令会自动检测安装来源（Git/pip），拉取最新版本，然后重新部署技能包和扩展。

## 4. 分析日志

```bash
# 用 @ 前缀传入文件
storageops --print @/path/to/rclone-debug.log '分析这个 rclone 日志'
```

## 5. 查看帮助

```bash
storageops --help
storageops --version
```

## 常见问题

**Q: 我已经有 Pi Coding Agent，会有冲突吗？**

A: 不会。默认安装到 `~/.storageops/`，与 `~/.pi/` 完全隔离。如需合并，运行 `storageops install --merge`。

**Q: 诊断时需要我提供 AK/SK 吗？**

A: 不需要！StorageOps 不会连接你的云账户。`scan_secrets` 工具会自动扫描并脱敏日志中的凭据。
