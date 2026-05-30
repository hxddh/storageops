# Case: Object Storage Mount as Hot Workspace

## Scenario

用户将 BOS 对象存储挂载为 OpenClaw workspace 持久化存储。相比本地 SSD，启动时间从 1 分钟增长到 ~3 分钟，对话反馈从 10s+ 增长到 ~1 分钟。30 并发开发环境下 git 操作概率导致 BOS 掉挂载，文件编辑响应时间数秒。

## What It Tests

- 是否正确识别 mount + workspace 场景
- 是否给出 metadata amplification 根因
- 是否推荐 local SSD + snapshot 架构而非继续用 mount
- 是否要求 evidence 而非无证据下结论

## Expected Diagnosis

category: mount_filesystem_workspace
root cause: metadata amplification from stat/open/list calls on FUSE mount
recommendation: local SSD for hot workspace, periodic snapshot to object storage

## Difficulty

medium

## Domains Tested

- mount_filesystem_workspace
- triage
