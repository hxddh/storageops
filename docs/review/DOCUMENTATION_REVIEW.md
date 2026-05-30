# Documentation Review

**Review Date:** 2026-05-30  
**Scope:** `README.md`, `AGENTS.md`, `CHANGELOG.md`, `skill-registry.yaml`, all `SKILL.md` files, `docs/examples/`, `storageops-core/README.md`

---

## 1. README.md

### 1.1 Accuracy Assessment

**Overstated capabilities:**

| README Claim | Actual State |
|---|---|
| "multi-turn evidence collection" | The agent does 1 turn per domain branch; `max_turns=5` is not used for real multi-turn reasoning |
| "AI-powered diagnostic agent" | Zero LLM calls; purely deterministic rule engine |
| "v0.1 complete" | pytest is broken; `eval --all` always fails; 3 logic bugs in core |
| Network endpoint diagnosis | Returns a manual investigation stub — no analysis performed |

**Accurate claims:**
- "offline-first" — verified true
- "zero external dependencies" — verified true
- "secret redaction by default" — verified true
- CLI command list (triage, analyze, report, eval, agent) — all five subcommands exist

### 1.2 Missing from README

1. **Current limitations section** — no mention that `storageops agent` is rule-based, not LLM
2. **Supported cloud providers** — only AWS patterns are covered; Alibaba, Tencent, GCP not mentioned
3. **Python version requirements** — supported range (3.9–3.13 per CI) not stated
4. **Directory structure explanation** — Skill Pack vs Core vs CLI relationship not explained for new contributors
5. **Known limitations** — no `s3:Get*` wildcard in policy analysis, no network endpoint analyzer, etc.

### 1.3 Quick-start Usability

**Tested:** The README's quick-start example (`pip install -e storageops-cli/` then `storageops triage`) works correctly.

**Gap:** The `storageops eval` example in README will fail for new users because `eval --all` always reports failures (naming mismatch issue).

---

## 2. AGENTS.md

### 2.1 Overall Quality: Good

`AGENTS.md` is well-structured and follows coding agent guidance best practices:
- Clear skill selection criteria
- Evidence-before-conclusion mandate
- Secret redaction mandate
- Manual-only command policy
- Read-only constraint

### 2.2 Issues

1. **Describes LLM agent behavior** that doesn't exist yet — the "multi-turn" and "context management" sections describe planned behavior, not current implementation. A coding agent reading AGENTS.md would correctly follow the behavior described, but users expecting the `storageops agent` command to behave that way will be confused.

2. **No versioning** — AGENTS.md has no version number. If the Skill Pack evolves, it's unclear which version of AGENTS.md a particular agent was instructed with.

3. **Skill routing table** — The routing table in AGENTS.md should match `skill-registry.yaml`. It currently does, but they are maintained independently (same divergence risk as `agent.py`'s hardcoded domain map).

---

## 3. CHANGELOG.md

### 3.1 Assessment

CHANGELOG exists but is thin. It mentions v0.1 milestones in general terms without specific commit-level detail.

**Gap:** The CHANGELOG claims v0.1 is complete, but this review has found:
- 3 verified logic bugs in core analyzers
- pytest broken (P0)
- eval --all broken (P0)
- 5 dead variables in agent.py
- network endpoint analyzer is a stub

A CHANGELOG entry claiming completion should only be written when the described scope is actually complete and tested.

**Recommendation:** Add an "In Progress" or "Known Issues" section to CHANGELOG for v0.1.

---

## 4. Skill SKILL.md Quality Review

### 4.1 Format Consistency

All 10 `SKILL.md` files follow the same general structure:
- `name`, `version`, `description`
- `when_to_use`
- `do_not_use` (missing in 3 skills)
- `safety_rules` (missing in 2 skills)
- `diagnosis_workflow`
- `output_requirements`
- `references`

**Inconsistency:** `storageops-triage` lacks `safety_rules`. `storageops-performance-diagnosis` and `storageops-lifecycle-cost` lack `do_not_use`.

### 4.2 Content Quality

| Skill | SKILL.md Quality | References Quality |
|---|---|---|
| storageops-triage | Good | No reference files confirmed |
| storageops-s3-protocol-compatibility | Good | Excellent (5 files) |
| storageops-cli-sdk-diagnosis | Excellent | Excellent (6 files) |
| storageops-performance-diagnosis | Good, missing baselines | Good (5 files) |
| storageops-mount-filesystem-workspace | Good | Good (5 files) |
| storageops-network-endpoint-access | Good | Good (5 files) |
| storageops-security-iam-policy | Very good | Good (5 files) |
| storageops-lifecycle-cost | Good | Excellent (5 files) |
| storageops-evidence-reporting | Excellent | Excellent (4 templates) |
| storageops-eval-golden-cases | Good | Good (3 files) |

### 4.3 Reference File Actionability

Most reference files follow a good pattern: brief intro → specific patterns → example commands → caveats. The `storageops-cli-sdk-diagnosis` references (awscli, boto3, bcecmd, obsutil, rclone, s5cmd) are the most practically useful — they include actual CLI flags and log message patterns.

The `storageops-mount-filesystem-workspace` references for POSIX semantics are good at describing limitations but do not include specific diagnostic commands for common tools (`s3fs -d`, `mountpoint-s3 --debug`, `goofys --debug-fuse`).

---

## 5. docs/examples/

**Current state:** 1 file — `end-to-end-rclone-corrupted-transfer.md`

This is the only end-to-end example demonstrating the full diagnostic workflow. It is well-written and follows the `storageops-evidence-reporting` template structure.

**Gaps:**
1. Only 1 example for 9 domains
2. The filename does not match the golden case ID (`rclone-corrupted-transfer`), breaking `eval --all`
3. No example for: access denied, clock skew, cost analysis, network diagnosis, performance, mount/workspace

**Recommendation:** Add at least one example per domain. Ensure filenames match golden case IDs exactly.

---

## 6. storageops-core/README.md

Brief but accurate. Describes the module structure and how to run smoke tests.

**Gap:** Does not explain why there are no `__init__.py` files or why `sys.path` manipulation is required. New contributors will be confused when they try to `from parsers.parse_rclone_log import parse` and get an ImportError.

---

## 7. Missing Documents

| Document | Priority | Purpose |
|---|---|---|
| `CONTRIBUTING.md` | P1 | Development setup, coding conventions, how to add a new Skill, how to add a new parser/analyzer |
| `SECURITY.md` | P1 | Security model, redaction policy, how to report vulnerabilities, what the tool will/won't do |
| `ARCHITECTURE.md` | P2 | Layer diagram, data flow, module responsibilities, packaging plan |
| `ROADMAP.md` | P2 | Official roadmap (vs scattered mentions in README) |
| `docs/examples/<domain>.md` for each domain | P2 | One example per domain |
| `storageops-core/DEVELOPMENT.md` | P3 | How to add a new parser, how to add a new analyzer, testing conventions |

---

## 8. Documentation Inconsistencies

| Location | Claim | Reality |
|---|---|---|
| README | "v0.1 complete" | pytest broken, eval broken, 3 logic bugs |
| README | "AI-powered agent" | Deterministic rule engine |
| README | Shows `storageops eval` example | `eval --all` always fails |
| pyproject.toml | `version = "1.0.0"` | Conflicts with README's v0.1 roadmap |
| AGENTS.md | "multi-turn reasoning" | Agent does single-pass domain routing |
| CHANGELOG | v0.1 milestone complete | See above |

---

## 9. Priority Fixes

| Priority | Action | File |
|---|---|---|
| P0 | Fix README's eval example (or note it's broken) | `README.md` |
| P1 | Add "Current Limitations" section to README | `README.md` |
| P1 | Write `SECURITY.md` | New file |
| P1 | Write `CONTRIBUTING.md` | New file |
| P1 | Clarify agent is rule-based in README and AGENTS.md | `README.md`, `AGENTS.md` |
| P2 | Fix pyproject.toml version to match README roadmap | `storageops-cli/pyproject.toml` |
| P2 | Add `do_not_use` sections to 3 skills | `SKILL.md` files |
| P2 | Add `safety_rules` to `storageops-triage` SKILL.md | `agents/skills/storageops-triage/SKILL.md` |
| P2 | Write `ARCHITECTURE.md` | New file |
| P2 | Add examples for each domain | `docs/examples/` |
| P3 | Add version number to `AGENTS.md` | `AGENTS.md` |
| P3 | Explain `sys.path` pattern in `storageops-core/README.md` | `storageops-core/README.md` |
