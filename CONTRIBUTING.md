# Contributing

StorageOps 欢迎贡献！本项目是一个 Pi Coding Agent 扩展包，贡献方式很简单。

## 贡献方式

### 贡献诊断技能

1. 在 `skills/` 下创建 `storageops-<domain>/SKILL.md`
2. 在 `skill-registry.yaml` 中注册
3. 提交 PR

### 贡献工具

编辑 `storageops_cli/extensions/storageops.ts`，使用 `pi.registerTool()` 注册新工具。

### 改进 CLI

编辑 `storageops_cli/__init__.py`。

## 开发设置

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
pip install -e .
storageops install
```

## 文档

- `README.md` — 用户文档
- `AGENTS.md` — AI Agent 开发指南
- `docs/` — 详细文档
- `skill-registry.yaml` — 技能注册表

## License

MIT
