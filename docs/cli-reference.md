# CLI 参考

## storageops — 主命令

```
storageops [pi args]
```

所有参数转发到 `pi`。常用参数：

| 参数 | 说明 |
|------|------|
| `--print`, `-p` | 非交互模式，处理完退出 |
| `--no-session` | 不保存会话记录 |
| `--provider <name>` | 指定 provider（deepseek, anthropic, openai, google...） |
| `--api-key <key>` | API key |
| `--model <id>` | 模型 ID（如 `deepseek/deepseek-v4-flash:off`） |
| `--continue`, `-c` | 恢复上次会话 |
| `--resume`, `-r` | 选择历史会话恢复 |
| `--skills <path>` | 额外 skills 目录 |
| `--append-system-prompt <text>` | 追加系统提示词 |
| `@<file>` | 读取文件内容作为上下文 |

## storageops install

```
storageops install [--merge] [--force]
```

一键安装到 `~/.storageops/`（独立）。

| 选项 | 说明 |
|------|------|
| `--merge`, `-m` | 合并安装到 `~/.pi/`，融入已有 Pi |
| `--force`, `-f` | 强制重装 |

检测逻辑：
- 如果 `~/.pi/agent/settings.json` 不存在 → 静默独立安装
- 如果存在 → 提示用户选择模式
- pi 版本 < 0.78.0 → 警告 + 升级建议

## API Key 配置

四种方式，任选其一：

| 方式 | 命令 | 说明 |
|------|------|------|
| A. 环境变量 | `export DEEPSEEK_API_KEY=sk-xxx` | 推荐，一劳永逸 |
| B. 本地文件 | `echo sk-xxx > ~/.storageops/agent/api-key && chmod 600 ~/.storageops/agent/api-key` | 不受 shell 影响，建议仅当前用户可读 |
| C. 命令行 | `storageops --api-key sk-xxx ...` | 每次传入 |
| D. Pi 内登录 | `storageops` → `/login` | Pi 原生 |

## storageops --version / -V

```
$ storageops --version
StorageOps v0.4.1  (pi: 0.78.0)
  独立安装: 是  (~/.storageops/agent)
  合并安装: 否  (~/.pi/agent)
```

## storageops --help / -h

打印帮助信息。

## 示例

```bash
# 交互式诊断
storageops

# 单次诊断
storageops --print 's5cmd 429 错误'

# 指定模型
storageops --model deepseek/deepseek-v4-flash:off --print '...'

# 分析日志文件
storageops --print @error.log '分析这个错误'

# 恢复上次会话
storageops -c

# 合并安装
storageops install --merge
```
