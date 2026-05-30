# End-to-End Example: rclone Corrupted on Transfer

This example walks through a complete StorageOps diagnostic flow, from raw
evidence to a structured diagnosis report. Use it to understand how Skills
chain together.

---

## Step 0: The Incident

A user reports:

> I'm using rclone to copy a large file between two S3-compatible storage
> providers. rclone reports "corrupted on transfer: md5 hash differ" but
> the file size is the same on both sides. What's wrong?

---

## Step 1: Triage (`storageops-triage`)

### Input classification

- **Input type:** log_file (rclone debug output) + natural_language
- **Scope:** single file copy, server-side (no data through client)

### Domain classification

The error `corrupted on transfer: md5 hash differ` points to:
- Primary: `cli_sdk_behavior` — rclone-specific behavior
- Secondary: `checksum_etag` — ETag format comparison

### Evidence quality

- `sufficient` — rclone debug log with exact ETag values, file sizes, config

### Safety scan

- No secrets in the evidence provided by user (rclone config has redacted AK/SK)
- No destructive actions requested
- Not clearly production — flag `env_risk: "unclear"`

### Triage output

```yaml
category: cli_sdk_behavior
confidence: 0.85
severity: medium
input_type: log_file
evidence_quality: sufficient
route_to: [storageops-cli-sdk-diagnosis]
safety_flags: []
```

---

## Step 2: Specialist Diagnosis (`storageops-cli-sdk-diagnosis`)

### Evidence extracted

From rclone debug log:

| Evidence | Value | Source |
|---|---|---|
| rclone version | v1.65.0 | Debug log header |
| Copy method | server-side copy | Log: "Copied (server-side copy)" |
| Source MD5 | `a1b2c3d4e5f6789012345678abcdef01` | 32 hex chars, no suffix |
| Destination MD5 | `a1b2c3d4e5f6789012345678abcdef01-3` | 32 hex chars + "-3" |
| File size | identical (not shown as mismatched) | No size diff error |
| Transfer type | server-side, no client data involved | Debug log |

### Analysis

**ETag format comparison:**

```
Source:  a1b2c3d4e5f6789012345678abcdef01      → single PUT ETag (plain MD5)
Dest:    a1b2c3d4e5f6789012345678abcdef01-3    → multipart ETag (MD5 of part MD5s)
```

The destination provider performed a server-side copy by internally using
multipart upload. The source object was uploaded as a single PUT (simple
MD5 ETag). The destination's ETag format includes `-3` suffix indicating
a 3-part multipart upload.

rclone compares the source MD5 (plain) with the destination ETag (multipart
format). The hashes match in the meaningful prefix (`a1b2c3...`), but the
format suffix `-3` causes rclone to report a mismatch.

This is NOT:
- Network corruption (server-side copy, no bits on the wire)
- Actual data corruption (the MD5 prefix matches)
- A provider bug (multipart ETag format is standard S3 behavior)

### Root cause

**`tool_sdk_incompatibility`** — rclone's default `--s3-use-multipart-etag=true`
compares full multipart ETag against source MD5. The destination provider used
multipart for server-side copy, generating a multipart-format ETag.

### Diagnosis output

```yaml
category: cli_sdk_behavior
subcategory: rclone
confidence: 0.90
severity: medium
root_cause_type: tool_sdk_incompatibility
evidence_quality: sufficient
```

---

## Step 3: Evidence Report (`storageops-evidence-reporting`)

The report below uses the `diagnosis-report.md` template.

---

# 诊断报告

**报告编号:** STORAGEOPS-DIAG-0001
**分类:** cli_sdk_behavior / rclone
**严重程度:** Medium
**置信度:** 0.90

## 摘要

rclone 在两个 S3-compatible provider 之间执行 server-side copy 时，因目标端使用 multipart upload 产生 `-N` 后缀格式 ETag，导致 rclone 的 multipart ETag 校验误报 `corrupted on transfer`。文件内容完整，非数据损坏。

## 问题现象

```text
ERROR : largefile.bin: corrupted on transfer: md5 hash differ
  "a1b2c3d4e5f6789012345678abcdef01"
  vs
  "a1b2c3d4e5f6789012345678abcdef01-3"
```

文件大小相同，server-side copy，数据未经过客户端网络传输。

## 诊断结论

rclone 默认启用了 `--s3-use-multipart-etag=true`，期望目标 ETag 与源 MD5 完全匹配。但目标 provider 的 server-side copy 内部使用了 multipart upload（3 个 part），生成了标准 S3 multipart ETag 格式 `MD5-of-part-MD5s-N`。MD5 前缀完全一致，`-3` 后缀是 ETag 格式差异，不表示数据损坏。

## 关键证据

| # | 证据 | 来源 | 相关性 |
|---|---|---|---|
| 1 | 源 ETag: `a1b2...01` (32 hex, 无后缀) | rclone debug | 单 PUT ETag = 完整文件 MD5 |
| 2 | 目标 ETag: `a1b2...01-3` (32 hex + "-3") | rclone debug | Multipart ETag，MD5 前缀匹配 |
| 3 | "Copied (server-side copy)" | rclone debug | 数据未经过客户端，排除网络损坏 |
| 4 | 文件大小相同 | rclone debug | 非截断上传 |

## 修复建议

1. **推荐: 关闭 multipart ETag 校验**
   ```
   rclone copy ... --s3-use-multipart-etag=false
   ```
   影响：不会验证目标 multipart 上传的完整性。如果 provider 支持
   additional checksum（CRC32C/SHA256），可以配合 `--checksum` 使用。

2. **备选: 忽略 checksum**
   ```
   rclone copy ... --ignore-checksum
   ```
   风险：完全跳过校验，仅在信任 provider 完整性时使用。

3. **手动验证（不依赖 rclone 校验）**
   ```bash
   # 下载源和目标的文件到本地，手工比对 MD5
   # manual-only: rclone cat source:bucket/largefile.bin | md5sum
   # manual-only: rclone cat dest:bucket/largefile.bin | md5sum
   ```

## 风险提示

- `--ignore-checksum` 会跳过所有文件的所有校验，不仅仅是 multipart ETag
- 如果 provider 确实存在数据损坏，跳过校验后损坏不会被发现

## 后续排查清单

- [x] 确认文件 MD5 前缀匹配，排除数据损坏
- [x] 确认非网络问题（server-side copy）
- [ ] 验证端到端数据完整性（下载双方文件后手工比对）
- [ ] 评估是否将 `--s3-use-multipart-etag=false` 设为默认配置
- [ ] 关注 rclone 版本更新是否修复此行为

---

## Step 4: What This Example Demonstrates

1. **Triage → Specialist → Report** pipeline works with real-looking inputs.
2. **Evidence is always cited** — every claim has a specific data source.
3. **Safety rules are followed** — no secrets, no destructive commands without `manual-only`.
4. **Confidence is qualified** — 0.90 because evidence is strong but a full download
   verification would increase to 1.0.
5. **Multiple hypotheses are evaluated and rejected** — network corruption, actual
   data corruption, provider bug all considered and ruled out.

---

## Running This Through the Eval Framework

This example output can be tested against `rclone-corrupted-transfer/expected.json`:

```bash
# Future v0.2+:
# storageops eval --case cases/rclone-corrupted-transfer --output diagnosis-rclone-example.md
```

Expected: **PASS** with score ≈ 0.90+. The output:
- Category matches `cli_sdk_behavior` ✓
- All `must_include_evidence_keywords` present ✓
- All `must_include_recommendation_keywords` present ✓
- No `must_not_include` matches ✓
- All required report sections present ✓
