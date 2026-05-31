# Diagnosis Report Template

## Usage

This is the standard diagnostic report template used by all StorageOps specialist
Skills. It provides a structured, evidence-based format for presenting diagnostic
findings.

---

# 诊断报告 (Diagnosis Report)

**报告编号 (Report ID):** STORAGEOPS-DIAG-XXXX
**生成时间 (Generated):** YYYY-MM-DD HH:MM UTC
**分类 (Category):** [primary_category] / [subcategory]
**严重程度 (Severity):** Critical | High | Medium | Low
**置信度 (Confidence):** [0.0–1.0]

---

## 摘要 (Summary)

[One paragraph describing the issue, the primary finding, and the impact.
This section should be understandable by both technical and non-technical readers.]

---

## 问题现象 (Symptoms)

### 用户报告 (User Report)
[What the user described, in their own words if available.]

### 观测到的问题 (Observed Symptoms)
- **Error messages:** [Exact error messages, status codes, response bodies]
- **Timing:** [When it started, frequency, pattern]
- **Scope:** [Affected buckets, objects, operations, users]
- **Environment:** [Provider, region, tool/version, access path]

### 影响评估 (Impact Assessment)
- [Current operational impact]
- [Potential escalation if unresolved]

---

## 诊断结论 (Diagnosis Conclusion)

### 主要根因 (Primary Root Cause)
[Detailed explanation of the primary root cause. This should cite specific evidence.]

### 次要因素 (Contributing Factors)
- [Factor 1 — explanation and evidence]
- [Factor 2 — explanation and evidence]
- [Factors ruled out — explanation for why]

### 分类 (Classification)
- **Category:** [from issue taxonomy]
- **Subcategory:** [if applicable]
- **Root cause type:** [e.g., misconfiguration, provider behavior, workload pattern, etc.]

---

## 置信度 (Confidence Assessment)

| Aspect | Assessment |
|---|---|
| Overall confidence | [0.0–1.0] |
| Evidence quality | Sufficient / Partial / Insufficient |
| Factors increasing confidence | [List factors] |
| Factors decreasing confidence | [List factors limiting certainty] |
| Additional evidence needed | [What would increase confidence] |

### 诊断局限与数据盲区 (Limitations & Blind Spots)

[声明此诊断存在的已知局限和数据盲区。必须如实标注，不可为提升置信度而隐瞒。]
- [局限 1: 例如 "未包含 CloudTrail 审计日志, 可能存在未被日志记录的 API 操作"]
- [局限 2: 例如 "仅基于采样时段, 未反映日间/周间流量波动"]
- [盲区 1: 例如 "从未被读取的冷数据不在此分析范围, 实际可降本空间可能更大"]

---

## 关键证据 (Key Evidence)

| # | Evidence | Source | Type | Relevance |
|---|---|---|---|---|
| 1 | [Description of evidence] | [Where it came from — log file, error message, config] | log / error / config / measurement | [Why this matters] |
| 2 | ... | ... | ... | ... |

---

## 根因排序 (Root Cause Ranking)

1. **[Root Cause 1]** — Confidence: [X%]
   - Evidence: [citation to evidence table]
   - Mechanism: [How this causes the symptoms]
2. **[Root Cause 2]** — Confidence: [Y%]
   - Evidence: [citation]
   - Mechanism: [explanation]
3. ...

---

## 验证命令 (Validation Commands)

Commands that can be used to validate the diagnosis. All are read-only unless
marked `manual-only`.

```bash
# Check [aspect 1]
<read-only command>

# Check [aspect 2]
<read-only command>

# [Destructive/test command] (manual-only: requires confirmation)
# manual-only: <command>
```

---

## 修复建议 (Remediation Recommendations)

### 建议 1: [Title] (Recommended)
- **Action:** [What to do]
- **Expected outcome:** [What should improve]
- **Risk:** [Low / Medium / High] — [explanation of risks]
- **Rollback:** [How to undo if needed]
- **Status:** `manual-only` — requires review before applying

### 建议 2: [Title]
- ...

---

## 风险提示 (Risk Notes)

### 当前风险 (Current State Risks)
- [Risk of not addressing the issue]
- [Potential for escalation]

### 变更风险 (Change Risks)
- [Risks associated with each recommendation]
- [Interactions with other systems or configurations]
- [Compatibility concerns]

### 安全考量 (Security Considerations)
- [Any security implications of the findings or recommendations]
- [Secret exposure: Yes / No — if yes, all redacted]

---

## 后续排查清单 (Next-Step Checklist)

- [ ] **Action item 1** — Rationale and expected outcome
- [ ] **Action item 2** — Rationale and expected outcome
- [ ] **Validate fix** — Use validation commands above to confirm resolution
- [ ] **Document results** — Update this report or create a follow-up note
- [ ] **Consider golden case** — Is this issue a candidate for `storageops-eval-golden-cases`?

---

## 附录 (Appendix)

### 使用的 Skill
- `storageops-triage`
- `[specialist-skill-name]`
- `storageops-evidence-reporting`

### 参考文献
- [Provider documentation URLs]
- [Related issues or previous reports]

### 量化影响评估 (Quantified Impact)

[如果适用，包含量化的影响评估。]\n- **影响范围:** [受影响的 object 数 / bucket 数 / 用户数]
- **时间恢复预估:** [预估修复时间]
- **成本影响 (估算):** [预估月/年财务影响, 注明假设价格]

### 脱敏声明 (Redaction Statement)
All secrets, credentials, tokens, and Authorization headers in this report
have been redacted as `[REDACTED]`. No real credentials are exposed.

---

**END OF REPORT**
