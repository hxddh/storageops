# Skill Pack Review

**Review Date:** 2026-05-30  
**Scope:** All 10 skills in `agents/skills/`, plus `skill-registry.yaml`

---

## 1. Registry Consistency

**Verified fact:** All 10 skills declared in `skill-registry.yaml` have a corresponding `SKILL.md` file in `agents/skills/`. No orphaned entries, no missing files.

**Verified fact:** `skill-registry.yaml` declares `priority: 0` for `storageops-triage` and `auto_route: true` — correct design to ensure triage runs first.

**Gap:** The `routes` field in `skill-registry.yaml` is never read by `agent.py` or `cli.py`. It is purely informational. (See `ARCHITECTURE_REVIEW.md` §3.6.)

---

## 2. Per-Skill Assessment

### 2.1 storageops-triage ★★★★☆

**Strengths:**
- Clear triage decision tree covering all 9 domains
- `when_to_use` and `do_not_use` sections are specific and actionable
- Explicitly instructs agent to ask for raw evidence before diagnosis
- `routing_logic` section maps symptoms to skills

**Gaps:**
- No explicit `safety_rules` section — the Skill guides routing but does not repeat the redaction/read-only contract
- No `output_requirements` section specifying what the triage output must contain
- `references/` directory was expected but not confirmed present (find output shows no files under `storageops-triage/references/`)

**Recommendation:** Add safety reminder (redaction, read-only) and output requirements. Add at least one reference file for triage decision criteria.

---

### 2.2 storageops-s3-protocol-compatibility ★★★★☆

**Strengths:**
- Covers the critical SigV4 surface well: credential chain, clock skew, canonical request, string-to-sign
- `ListObjects` v1/v2 distinction documented
- Multipart upload ETag composition (part ETags → final ETag) is accurately described
- References cover the five most critical areas: `aws-s3-baseline`, `checksum-etag`, `list-objects`, `multipart-upload`, `sigv4`

**Gaps:**
- No explicit coverage of `x-amz-content-sha256: UNSIGNED-PAYLOAD` vs chunked encoding differences — a common compatibility issue with non-AWS SDKs
- No coverage of `Transfer-Encoding: chunked` vs `Content-Length` incompatibility
- The `checksum-etag` reference likely covers CRC32/SHA256 checksums but this is not confirmed from `SKILL.md` text alone

**Risk:** Medium — the skill is comprehensive for AWS, but third-party storage (Baidu BOS, Alibaba OSS) compatibility differences are not explicitly covered despite `bcecmd` appearing in the CLI SDK skill.

---

### 2.3 storageops-cli-sdk-diagnosis ★★★★★

**Strengths:**
- Covers 6 CLI tools: awscli, boto3, bcecmd, rclone, obsutil, s5cmd
- Each tool has a dedicated `references/*.md` file — best-maintained reference set in the entire Skill Pack
- `scripts/README.md` provides diagnostic script templates
- Correctly distinguishes between client-side errors (config, credential chain) and server-side errors (4xx, 5xx)

**No significant gaps identified.** This is the most complete Skill in the pack.

---

### 2.4 storageops-performance-diagnosis ★★★☆☆

**Strengths:**
- Good coverage of throughput model, prefix hotspot, small-files penalty, throttling patterns
- References cover the key performance topics

**Gaps:**
- No explicit benchmark baselines (e.g., "expected single-stream throughput for 1GB file in same-region = X MB/s") — makes it hard to calibrate "slow" vs "expected slow"
- No coverage of IOPS vs bandwidth distinction for mixed workloads
- Multipart tuning reference exists but the SKILL.md does not specify minimum evidence required before recommending multipart reconfiguration
- Missing `do_not_use` section — when should the agent NOT use this skill?

**Risk:** Without baselines, the skill may produce recommendations that contradict actual expectations for the user's specific cloud provider or tier.

---

### 2.5 storageops-mount-filesystem-workspace ★★★☆☆

**Strengths:**
- POSIX semantics gap coverage is accurate (no atomic rename, eventual consistency, no hard links, etc.)
- Agent/sandbox storage use case is explicitly addressed
- `workspace-layout` reference is a useful practical guide

**Gaps:**
- No coverage of `s3fs` vs `goofys` vs `mountpoint-s3` behavioral differences
- No explicit handling of metadata caching (`stat_cache_expire`, `entry_cache_expire`) tuning — the most common source of "stale file" issues
- `run_analysis()` in `agent.py` for `mount_filesystem_workspace` domain **ignores input text entirely** and returns a hardcoded default syscall profile. This means the Skill's guidance is never actually applied by the current implementation.

**Risk:** High mismatch between Skill promise and implementation. The Skill describes evidence-based diagnosis, but the actual analysis ignores the evidence.

---

### 2.6 storageops-network-endpoint-access ★★☆☆☆

**Strengths:**
- Five reference documents cover the right topics: DNS/host header, endpoint routing, private access, TLS/MTU/RTT, cross-cloud dedicated line
- `dns-host-header` reference likely covers the `virtual-hosted-style` vs `path-style` distinction

**Critical Gap:**
- **There is no functional analyzer.** The CLI returns a stub for this domain. The Skill has documentation but zero implementation behind it.
- No `safety_rules` about DNS-based evidence collection
- No coverage of IPv6 dual-stack endpoint issues

**Recommendation:** Either implement the analyzer or explicitly mark the skill as "documentation-only, requires manual investigation" with a timeline for implementation.

---

### 2.7 storageops-security-iam-policy ★★★★☆

**Strengths:**
- Explicitly covers: cross-account, STS, bucket policy vs IAM policy evaluation order, KMS SSE
- `secret-redaction` reference documents the redaction protocol — good that it's a first-class reference
- `access-denied` reference likely covers the `NotAuthorized` vs `AccessDenied` distinction

**Gaps:**
- Policy evaluation for organization SCPs (Service Control Policies) not mentioned
- No explicit guidance on what evidence to collect when the user does NOT have admin access (common in enterprise scenarios)

**Safety:**
- `analyze_policy.py` does NOT handle `s3:Get*` prefix wildcards — a common policy pattern that will be silently misdiagnosed. (See `CORE_CODE_REVIEW.md` §3.3.)

---

### 2.8 storageops-lifecycle-cost ★★★☆☆

**Strengths:**
- 5 reference documents covering: intelligent tiering, inventory analysis, lifecycle rules, request cost, storage classes
- `small-files` reference is particularly valuable given the IA minimum billable size gotcha
- Cost penalty calculation framework exists in `analyze_cost.py`

**Gaps:**
- No mention of cross-region replication cost in the SKILL.md (replication doubles storage + adds per-GB transfer cost)
- No guidance on how to estimate savings vs migration cost for Intelligent-Tiering adoption
- The `avg_object_age_days=0` false-positive bug in `analyze_cost.py` means the Skill's guidance about minimum duration risks may fire for all new data (see `CORE_CODE_REVIEW.md` §3.4)

---

### 2.9 storageops-evidence-reporting ★★★★★

**Strengths:**
- 4 output templates: `customer-report`, `diagnosis-report`, `internal-engineering-note`, `reproduction-checklist`
- Template structure encourages evidence citation before conclusions
- `reproduction-checklist` template is a practical addition often missing from diagnostic tools
- The distinction between internal vs customer-facing reports is well-considered

**No significant gaps identified.** This is the second strongest Skill alongside `storageops-cli-sdk-diagnosis`.

---

### 2.10 storageops-eval-golden-cases ★★★☆☆

**Strengths:**
- 5 golden cases covering diverse scenarios: access denied, clock skew, corrupted transfer, cost, mount performance
- `expected.json` schema per case enables automated scoring
- 3 reference documents: `eval-rubric`, `golden-case-format`, `unsafe-output-rules`

**Critical Gap:**
- The `unsafe-output-rules` reference defines patterns, but `eval_runner.py`'s `scan_unsafe()` function has a known false positive: `--no-sign-request` in a `# manual-only:` prefixed code block is flagged as unsafe. This means a correctly-formatted SKILL.md validation section would fail the eval gate.
- 5 golden cases is too few for the stated goal of constraining quality. At minimum, each major domain should have 2+ cases (positive + negative/edge case).
- `scripts/README.md` exists but likely only documents manual eval execution, not automated batch runs.

---

## 3. Cross-Skill Issues

### 3.1 Safety rules inconsistency
Some skills have explicit `safety_rules` sections listing what the agent must NOT do. Others (notably `storageops-triage`, `storageops-performance-diagnosis`) lack this. The safety contract should be uniform across all skills.

### 3.2 Missing `do_not_use` in several skills
`storageops-performance-diagnosis`, `storageops-mount-filesystem-workspace`, and `storageops-lifecycle-cost` lack `do_not_use` sections. Without these, the triage logic may route to these skills in inappropriate contexts.

### 3.3 Evidence requirement thresholds not specified
Most skills describe what evidence to collect but do not specify the minimum evidence required to produce a finding vs "insufficient evidence." This creates risk of low-evidence conclusions.

---

## 4. Skill Quality Matrix

| Skill | Completeness | Safety | References | Implementation Match | Score |
|---|---|---|---|---|---|
| storageops-triage | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ | 3.5/5 |
| storageops-s3-protocol-compatibility | ★★★★☆ | ★★★★☆ | ★★★★★ | ★★★★☆ | 4.0/5 |
| storageops-cli-sdk-diagnosis | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★★ | 4.7/5 |
| storageops-performance-diagnosis | ★★★☆☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | 3.3/5 |
| storageops-mount-filesystem-workspace | ★★★☆☆ | ★★★★☆ | ★★★★☆ | ★★☆☆☆ | 3.0/5 |
| storageops-network-endpoint-access | ★★★☆☆ | ★★★☆☆ | ★★★★☆ | ★☆☆☆☆ | 2.5/5 |
| storageops-security-iam-policy | ★★★★☆ | ★★★★★ | ★★★★☆ | ★★★★☆ | 4.0/5 |
| storageops-lifecycle-cost | ★★★☆☆ | ★★★★☆ | ★★★★★ | ★★★☆☆ | 3.3/5 |
| storageops-evidence-reporting | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ | 5.0/5 |
| storageops-eval-golden-cases | ★★★☆☆ | ★★★★☆ | ★★★★☆ | ★★★☆☆ | 3.3/5 |

---

## 5. Priority Fixes

| Priority | Skill | Action |
|---|---|---|
| P1 | storageops-network-endpoint-access | Implement `analyze_network_endpoint.py` or add "not yet implemented" disclaimer |
| P1 | storageops-eval-golden-cases | Fix `scan_unsafe()` false positive for `manual-only:` prefixed commands; add 10+ more golden cases |
| P1 | storageops-mount-filesystem-workspace | Fix `run_analysis()` in `agent.py` to actually use input text for this domain |
| P2 | All skills | Add `safety_rules` section to any skill missing it |
| P2 | storageops-performance-diagnosis | Add benchmark baselines; add `do_not_use` section |
| P2 | storageops-triage | Add `output_requirements`; add `references/` directory |
| P3 | storageops-lifecycle-cost | Add cross-region replication cost guidance |
| P3 | storageops-s3-protocol-compatibility | Add chunked encoding vs Content-Length compatibility note |
