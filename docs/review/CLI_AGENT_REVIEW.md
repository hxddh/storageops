# CLI and Agent Review

**Review Date:** 2026-05-30  
**Scope:** `storageops-cli/storageops/cli.py`, `storageops-cli/storageops/agent.py`, `storageops-cli/storageops/__init__.py`, `storageops-cli/pyproject.toml`

---

## 1. CLI Installation and Packaging

### 1.1 Installation

**Verified fact:** `pip install -e storageops-cli/` succeeds. Version `1.0.0` installs correctly. The `storageops` command becomes available in PATH after installation.

**Concern:** `pyproject.toml` declares `version = "1.0.0"` but the project is clearly pre-1.0 functionality. This version number conflicts with semantic versioning conventions and the README's stated roadmap (v0.1 → v0.2 → v0.3 → v1.0). The installed CLI package claims to be v1.0 while the README says v0.1 is current.

**Recommendation:** Align `pyproject.toml` version with the README roadmap version (e.g., `0.1.0`).

---

### 1.2 pyproject.toml

**Verified fact:** `dependencies = []` — correct, since `storageops-core` has no external dependencies and is imported via `sys.path` rather than as a package dependency.

**Gap:** `storageops-core` is not declared as a dependency even though the CLI requires it. If `storageops-cli` is installed into a fresh virtualenv without the `storageops-core` directory present at the expected relative path, all imports fail with `ModuleNotFoundError`. The packaging does not encode the relationship between the two packages.

---

## 2. CLI Commands

### 2.1 storageops triage

**Verified fact:** `storageops triage --help` works. Accepts `--input` file path or stdin.

**Behavior:**
- `auto_detect()` computes domain confidence using: `min(score / max(1, len(SIGNATURES[domain])), 0.95)`
- The denominator is `len(SIGNATURES[domain])` — total number of signature patterns for the domain, NOT the number that matched
- Result: 1 match out of 8 patterns gives confidence = 0.125; 2 matches out of 8 gives 0.25
- The 0.95 cap means even an exact match of all patterns cannot produce 100% confidence

**Issue:** The confidence formula is not calibrated — it is structurally sensitive to the number of patterns defined per domain. A domain with 2 patterns has a maximum confidence of 1.0 (1 match → 0.50, 2 matches → 1.0 → capped at 0.95), while a domain with 16 patterns has a maximum of 0.95 (16/16). This means adding diagnostic patterns LOWERS maximum achievable confidence.

**Recommendation:** Use `matched_count / total_matched_signals` or an F-score approach rather than `matched / total_patterns`.

**`evidence_quality` threshold:** Set to `"sufficient"` if `primary_confidence >= 0.5`, else `"partial"`. This binary threshold with no nuance is acceptable for v0.1 but should be replaced with graduated quality levels.

---

### 2.2 storageops analyze

**Verified fact:** Routes to correct analyzer based on `--domain` parameter or auto-detected domain.

**Gap (P1):** `network_endpoint_access` domain returns a stub without invoking any parser or analyzer:
```python
result = {"domain": "network_endpoint_access", "status": "manual_investigation_required", ...}
```
This means the `analyze` command provides no value for network/endpoint problems.

**Gap (P2):** `parse_s5cmd_log.py` is only wired into `performance_throughput` domain, not into `cli_sdk_diagnosis` or `s3_protocol_compatibility`. Users with s5cmd errors in non-throughput contexts get no analysis.

---

### 2.3 storageops report

**Verified fact:** Accepts `--input` JSON from `storageops analyze` output and produces Markdown report.

**Issue:** `cmd_report()` truncates the report at **3000 characters** via `report_text[:3000]`. This is an arbitrary hard limit that silently truncates complex reports. The truncation is not communicated to the user.

**Security concern:** `cmd_report()` builds the report by string interpolation of analysis JSON values without sanitization. If an attacker-controlled log file contains Markdown injection payloads in field values, those would propagate into the report. The impact is limited (no execution) but the report integrity is affected.

**Gap:** No `--output` file flag — reports always go to stdout. For integration with ticketing systems or file-based workflows, this is limiting.

---

### 2.4 storageops eval

**Critical bug (P0):**
`storageops eval --all` always reports failures for the provided examples directory. The one existing example file (`docs/examples/end-to-end-rclone-corrupted-transfer.md`) does not match the expected naming pattern (`rclone-corrupted-transfer.md` based on the golden case ID).

**Evidence:**
- Golden case ID: `rclone-corrupted-transfer` (from `agents/skills/storageops-eval-golden-cases/cases/rclone-corrupted-transfer/`)
- Actual example filename: `end-to-end-rclone-corrupted-transfer.md`
- `eval_runner.py` matches by exact case ID, not by substring

**Impact:** Every `eval --all` run reports 5/5 failures. This makes the eval command useless for quality assurance in CI.

**Fix:** Either rename `end-to-end-rclone-corrupted-transfer.md` to `rclone-corrupted-transfer.md`, or implement slug normalization in `cmd_eval()`.

---

### 2.5 storageops agent

**Verified fact:** Installs and runs. `storageops agent --help` works. Accepts `--domain`, `--input`, `--max-turns` parameters.

**Critical issue (architecture):** This is not an LLM agent. It is a deterministic rule-based orchestrator. See `ARCHITECTURE_REVIEW.md` §3.2 for full analysis.

---

## 3. Agent Implementation Review

### 3.1 Dead variables (ruff F841 — 5 violations in agent.py)

| Variable | Location | Reason Unused |
|---|---|---|
| `helpful` | `classify_evidence()` line ~180 | Never read after assignment |
| `found_count` | `classify_evidence()` line ~182 | Never incremented or read |
| `has_config` | `assess_evidence()` line ~210 | Never read after assignment |
| `has_timing` | `assess_evidence()` line ~213 | Never read after assignment |
| `has_tool` | `assess_evidence()` line ~216 | Never read after assignment |

**Impact:** `classify_evidence()` always returns `evidence_quality: 'partial'` for all known domains (comment: "Simplified: we assume partial until interactive"). The function body is mostly dead code. However, the agent loop uses `assess_evidence()` (not `classify_evidence()`) for the quality gate, so runtime behavior is not affected.

**Recommendation:** Remove the dead variables. Either implement real evidence classification or simplify `classify_evidence()` to return `'partial'` unconditionally with a `# TODO: implement with LLM` comment.

---

### 3.2 run_analysis() for mount_filesystem_workspace ignores input (P1)

**Verified fact:** The `mount_filesystem_workspace` branch in `run_analysis()` returns a hardcoded default analysis dict regardless of the input text content. The input text is parsed (the function calls `parse_mount_info(text)`) but the result is not used — only the hardcoded `DEFAULT_SYSCALL_PROFILE` is returned.

**Impact:** A user who pastes a mount config showing a specific problem (e.g., `allow_other=false`) receives the same default analysis as a user who provides no mount config at all.

---

### 3.3 Evidence checklist duplication (P2)

`agent.py` contains `EVIDENCE_CHECKLIST` with per-domain checklists. These duplicate (with different granularity) the evidence requirements in each Skill's `SKILL.md`. When a Skill is updated, the agent's checklist does not automatically update. Over time these will diverge.

---

### 3.4 report generation mutation (P3)

`generate_report()` calls `analysis.pop('_secret_scan', {})` then later `analysis['_secret_scan'] = secret_scan` to restore it. This in-place mutation of the input dict means calling `generate_report()` twice on the same dict produces different output the second time (second call sees the restored `_secret_scan` key but may double-process it if the structure has changed).

---

### 3.5 f-strings without placeholders (ruff F541 — 4 violations)

Lines 281, 535, 553, 568 contain `f"..."` strings without any `{...}` placeholders. These are plain strings with no interpolation and should be plain string literals `"..."`. Cosmetic issue only.

---

## 4. Security Flags

### 4.1 --no-redact flag lacks security warning (P1)

**Evidence:** `cli.py:429`:
```python
parser.add_argument('--no-redact', action='store_true', help="disable secret redaction")
```

No warning is displayed when `--no-redact` is used. A user running `storageops report --no-redact > report.md` and sharing the report could inadvertently expose AWS access keys, session tokens, or Authorization headers present in the analyzed log.

**Recommendation:** Print a `WARNING: Secret redaction is disabled. Do not share output containing raw credentials.` message to stderr when `--no-redact` is activated.

---

## 5. CLI Usability Matrix

| Feature | Status | Notes |
|---|---|---|
| Installs via pip | ✅ | Works |
| `storageops --help` | ✅ | All 5 subcommands listed |
| `storageops triage` | ✅ | Works; confidence formula has issues |
| `storageops analyze` | ⚠️ | Works for 8/9 domains; network stub |
| `storageops report` | ⚠️ | Works; 3000-char truncation; no `--output` flag |
| `storageops eval` | ❌ | `--all` always fails due to naming mismatch |
| `storageops agent` | ⚠️ | Runs; not an LLM agent; 5 dead variables |
| JSON output | ✅ | All commands support `--format json` |
| Markdown output | ✅ | `storageops report` produces Markdown |
| Exit codes | ✅ | `sys.exit(1)` on error; `0` on success |
| Large file handling | ⚠️ | No input size limit; 100MB log would be processed in memory |
| Multi-case batch | ❌ | No batch mode; one input per invocation |

---

## 6. Priority Fixes

| Priority | Item | File | Action |
|---|---|---|---|
| P0 | eval --all naming mismatch | `eval_runner.py` / `docs/examples/` | Rename example file or implement slug normalization |
| P1 | network_endpoint_access stub | `cli.py`, `analyzers/` | Implement analyzer |
| P1 | --no-redact security warning | `cli.py:429` | Add stderr warning |
| P1 | pyproject.toml version mismatch | `storageops-cli/pyproject.toml` | Change `1.0.0` → `0.1.0` |
| P2 | report 3000-char truncation | `cli.py cmd_report()` | Make configurable or remove |
| P2 | triage confidence formula | `cli.py auto_detect()` | Use matched/matched_max ratio |
| P2 | Dead variables in agent.py | `agent.py` | Remove or implement |
| P2 | mount_filesystem_workspace ignores input | `agent.py run_analysis()` | Use parsed input in analysis |
| P3 | f-strings without placeholders | `agent.py` | Convert to plain strings |
| P3 | generate_report() mutation | `agent.py` | Use `dict(analysis)` copy |
