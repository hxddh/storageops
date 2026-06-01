# Case: Small Files in Standard-IA Causing Cost Amplification

## Scenario

用户发现 S3 月费用异常高，但实际存储数据量只有 10 GB。检查发现 1000 万个 1 KB 小文件被 lifecycle rule 迁移到了 Standard-IA，每 KB 被按 128 KB 计费，实际账单存储量为 1280 GB。

## What It Tests

- 正确识别 Standard-IA minimum billable size (128 KB)
- 识别 lifecycle 将小文件迁移到 IA 是成本反模式
- 建议修改 lifecycle rule 避免小文件进入 IA
- 不误判为 provider 计费错误

## Expected Diagnosis

category: lifecycle_cost / subcategory: small_object_cost
root cause: lifecycle rule 将所有文件迁移到 Standard-IA，但小文件 (<128KB) 被按 128KB 最小计费，导致存储费用 128x 放大
recommendation: 修改 lifecycle rule 用 filter 排除小文件，或聚合小文件后再迁移

## Difficulty

medium

## Domains Tested

- lifecycle_cost
- storage_class
- triage
