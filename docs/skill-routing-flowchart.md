# StorageOps Skill Routing Flowchart

```
用户描述对象存储问题
        │
        ▼
┌───────────────────────────────────────────┐
│          storageops-triage                │
│  分类 · 严重性评估 · 证据缺口 · 路由       │
│  时间模式检测 · 交叉域排查                  │
└──────┬──────┬──────┬──────┬──────┬───────┘
       │      │      │      │      │
       ▼      ▼      ▼      ▼      ▼
   ┌──────┐┌─────┐┌──────┐┌─────┐┌──────────┐
   │协议  ││权限 ││性能  ││网络 ││  CLI/SDK  │
   │s3-   ││sec- ││perf- ││net- ││  cli-     │
   │proto ││urity││orm   ││work ││  sdk      │
   └──┬───┘└──┬──┘└──┬───┘└──┬──┘└────┬─────┘
      │       │      │       │        │
      │ 交叉域: 403+签名→ s3-proto      │
      │ 交叉域: ETag→ s3-proto ←───────┘
      │       
      ▼      ▼      ▼       ▼        ▼
   ┌──────┐┌─────┐┌──────┐┌─────┐┌──────────┐
   │挂载  ││成本 ││复制  ││日志 ││          │
   │mount ││life-││repl- ││access││          │
   │      ││cycle││cation││log  ││          │
   └──┬───┘└──┬──┘└──┬───┘└─────┘└──────────┘
      │       │      │
      │ 交叉域: metadata → perf        │
      └───────┴──────┴──────────────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ evidence-reporting  │
         │   结构化诊断报告     │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │ eval-golden-cases   │
         │   质量回归验证       │
         └─────────────────────┘
```

## 常见症状 → Skill 速查

| 症状 | 主 Skill | 可能 Cross |
|------|---------|-----------|
| SignatureDoesNotMatch | s3-protocol-compatibility | security (403) |
| 403 AccessDenied | security-iam-policy | s3-protocol (签名) |
| corrupted on transfer | cli-sdk-diagnosis | s3-protocol (ETag) |
| 429 SlowDown | performance-diagnosis | — |
| 上传/下载慢 | performance-diagnosis | network (RTT) |
| mount 挂载慢/hang | mount-filesystem-workspace | performance |
| 端点不通 | network-endpoint-access | — |
| 成本异常 | lifecycle-cost | — |
| 复制延迟 | replication-versioning | network |
| TLS 证书错误 | network-endpoint-access | — |
| CORS 前端报错 | s3-protocol-compatibility | — |
| Object Lock 冲突 | replication-versioning | — |
| 访问日志/错误率尖峰 | access-log-analysis | security / performance / lifecycle-cost |
