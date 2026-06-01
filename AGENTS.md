# AGENTS.md — StorageOps for AI Agents

这是 StorageOps 项目的 AI Agent 开发指南。

## 项目定位

StorageOps 是一个 **Pi Coding Agent 扩展包**，不包含 Python agent 代码。
所有 agent 能力（agent loop、session、tool dispatch、UI）由 Pi 原生提供。

## 目录结构

```
storageops/
├── storageops_cli/               ← thin CLI shim
│   ├── __init__.py               ← install / launch logic (240 行)
│   ├── extensions/storageops.ts  ← 3 inline TypeScript 工具 (359 行)
│   └── skills/                   ← 符号链接 → repo root skills/
├── skills/                        ← 16 个诊断技能包
│   ├── storageops-triage/
│   ├── storageops-security-iam-policy/
│   └── ...
├── docs/
└── pyproject.toml
```

## 修改指南

### 增加诊断工具

编辑 `storageops_cli/extensions/storageops.ts`：

```typescript
pi.registerTool({
  name: "my_tool",
  label: "My Tool",
  description: "...",
  parameters: Type.Object({ ... }),
  async execute(_toolCallId, params) {
    return { content: [{ type: "text", text: "result" }] };
  },
});
```

所有工具在 Pi TypeScript 运行时内联执行，无需 Python subprocess。

### 增加/修改技能包

1. 在 `skills/` 下创建 `storageops-<domain>/SKILL.md`
2. YAML frontmatter 格式参考已有技能
3. 更新 `skill-registry.yaml`
4. 不需要改代码

### 修改 CLI 安装逻辑

编辑 `storageops_cli/__init__.py`，`cmd_install()` 函数。

## 测试

```bash
# 本地独立安装测试
pip install -e .
storageops install --force

# 合并安装测试
storageops install --merge --force

# 诊断功能测试
storageops --print --no-session --api-key sk-xxx 'test query'
```
