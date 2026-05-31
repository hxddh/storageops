# Test and Eval Review

**Review Date:** 2026-05-30  
**Scope:** `storageops-core/tests/smoke_test.py`, `tests/validation/`, `agents/skills/storageops-eval-golden-cases/`, `.github/workflows/ci.yml`

---

## 1. Test Infrastructure Overview

| Component | Type | Count | Status |
|---|---|---|---|
| `smoke_test.py` | Standalone script | 7 assertions | PASS (standalone); CRASH (pytest) |
| `run_validation.py` | Integration test script | 5 validation inputs | PASS (standalone); not in pytest |
| Golden cases | Eval cases with expected.json | 5 cases | Usable manually; `eval --all` broken |
| docs/examples | Example outputs for eval | 1 file | Naming mismatch |
| pytest suite | pytest test collection | 0 tests | INTERNALERROR on every run |
| CI workflow | GitHub Actions | 1 workflow | Runs smoke+validation; skips pytest+ruff |

---

## 2. pytest Situation (P0 Critical)

### 2.1 Root Cause

`storageops-core/tests/smoke_test.py` calls `sys.exit(0)` at module level (the final statement in the file). When pytest imports this file during test collection, the Python process terminates immediately.

**Verified:** Running `pytest -q` produces:
```
INTERNALERROR> SystemExit: 0
```

No tests run. No test results. pytest is completely broken.

### 2.2 Secondary Issues

- Functions are named `check_X()` not `test_X()` — pytest would not collect them even without the sys.exit issue
- No `conftest.py` — no shared fixtures
- No `@pytest.mark.*` decorators
- No pytest configuration in `pyproject.toml` or `pytest.ini`

### 2.3 Fix Plan

```python
# smoke_test.py — minimal changes to make pytest-compatible
def test_secret_scanner_detects_akia():  # rename check_ → test_
    result = scan(SAMPLE_WITH_AKIA)
    assert result['found_count'] > 0, "Should detect AKIA"

# Remove the module-level execution block or guard it:
if __name__ == '__main__':
    # ... existing test runner ...
    sys.exit(0 if all_passed else 1)
```

---

## 3. Validation Test Suite

### 3.1 run_validation.py

**Verified fact:** Runs successfully as a standalone script. Processes 5 input files in `tests/validation/inputs/`, exits 0 when all pass.

**Input files:**
| File | Tests |
|---|---|
| `awscli-works-s5cmd-fails.txt` | Domain detection: s5cmd errors should route to cli_sdk_diagnosis |
| `minimal-slow.txt` | Minimal throughput input |
| `mixed-403-throttle.log` | Mixed 403 + throttling signals |
| `secrets-in-log.log` | Secret detection and redaction |
| `truncated-rclone-batch.log` | Truncated rclone output handling |

**Gap:** `run_validation.py` inserts `storageops-core/analyzers` path **twice** into `sys.path` (line ~20). Minor redundancy, no functional impact.

**Gap:** The validation suite tests input → domain routing but does NOT validate:
- Analyzer output correctness
- Report format correctness
- Eval score against expected

---

## 4. Golden Cases

### 4.1 Case Coverage

| Case | Domain | Has expected.json | Has input files |
|---|---|---|---|
| `access-denied-cross-account` | security_iam_policy | ✅ | `description.md` only |
| `rclone-corrupted-transfer` | s3_protocol_compatibility | ✅ | `rclone-debug.log` |
| `signature-clock-skew` | s3_protocol_compatibility | ✅ | awscli debug log + error XML + system info |
| `small-files-ia-cost` | lifecycle_cost | ✅ | lifecycle XML + user description |
| `workspace-mount-slow-git` | mount_filesystem_workspace | ✅ | mount config + timing data + user description |

**Total: 5 cases for 9 domains.** Four domains have zero golden cases:
- `triage` (meta-skill)
- `network_endpoint_access`
- `cli_sdk_diagnosis`
- `performance_throughput`

### 4.2 expected.json Schema

Each `expected.json` contains:
- `category` — expected domain classification
- `required_findings` — list of expected finding IDs
- `forbidden_findings` — findings that must NOT appear
- `min_score` — minimum acceptable eval score
- `unsafe_output` — whether unsafe output is expected (should always be `false`)

**Good design.** The schema is appropriate for automated scoring.

### 4.3 Eval Scoring (eval_runner.py)

Scoring weights (verified from code):
- `category_match`: weight 0.0 (hard gate, evaluated separately)
- `required_findings_present`: weight 0.40
- `forbidden_findings_absent`: weight 0.25
- `evidence_quality`: weight 0.20
- `report_structure`: weight 0.15
- `unsafe_output`: weight 0.0 (hard gate)

**Total weighted = 1.00.** Weights sum correctly.

**Issue:** A score of 0.79 (all required findings + no forbidden findings + sufficient evidence but poor structure) would be considered "passing" if `min_score = 0.7`. But a report with hallucinated findings not in the forbidden list would also pass. The `forbidden_findings` list relies on being comprehensive — if a new failure mode hallucination type is not anticipated, it won't be caught.

---

## 5. CI Workflow Analysis

### 5.1 Current .github/workflows/ci.yml

| Step | Command | Status |
|---|---|---|
| Matrix: Python 3.9–3.13 | — | ✅ |
| Install | `pip install -e storageops-cli/` | ✅ |
| Smoke test | `python storageops-core/tests/smoke_test.py` | ✅ |
| Validation | `python tests/validation/run_validation.py` | ✅ |
| Agent rclone test | `storageops agent --domain s3_protocol_compatibility` | ✅ |
| Agent secrets test | `storageops agent` with secrets log | ✅ |
| Triage assertion | `storageops triage` with mixed log | ✅ |

**What CI does NOT run:**
- `pytest` (broken, correctly avoided)
- `ruff check .` (24 violations currently)
- `storageops eval --all` (would always fail)
- `mypy .` (no type annotations, would likely fail)
- Any installation test for `storageops-core` as a standalone package

### 5.2 CI Gaps

1. **No lint check** — 24 ruff violations never caught by CI
2. **No pytest** — when smoke_test.py is fixed, CI should run `pytest -q`
3. **No eval gate** — CI does not validate diagnostic quality
4. **No type checking** — no mypy or pyright in CI
5. **No cross-platform test** — CI only runs on ubuntu-latest

---

## 6. Test Coverage Matrix

| Module | Unit Test | Smoke Test | Validation | Eval Golden Case |
|---|---|---|---|---|
| `parse_awscli_debug` | ❌ | ✅ | ✅ (awscli-works file) | ✅ (clock-skew case) |
| `parse_rclone_log` | ❌ | ✅ | ✅ | ✅ (corrupted-transfer) |
| `parse_lifecycle_xml` | ❌ | ❌ | ❌ | ✅ (small-files-ia) |
| `parse_s5cmd_log` | ❌ | ❌ | ❌ | ❌ |
| `parse_s5cmd_error` | ❌ | ❌ | ❌ | ❌ |
| `parse_sigv4_error` | ❌ | ✅ | ✅ | ✅ (clock-skew) |
| `detect_throttling` | ❌ | ❌ | ✅ (mixed-403 file) | ❌ |
| `analyze_policy` | ❌ | ✅ | ❌ | ✅ (access-denied) |
| `analyze_cost` | ❌ | ✅ | ❌ | ✅ (small-files-ia) |
| `analyze_throughput` | ❌ | ❌ | ✅ (minimal-slow) | ❌ |
| `analyze_metadata_amplification` | ❌ | ❌ | ❌ | ❌ |
| `eval_runner` | ❌ | ❌ | ❌ | meta |
| `secret_scanner` | ❌ | ✅ | ✅ (secrets log) | ❌ |

**No module has a unit test.** Everything is tested via integration-style smoke tests or standalone scripts.

---

## 7. Priority Gaps to Fill

| Priority | Gap | Suggested Test |
|---|---|---|
| P0 | pytest broken | Fix `smoke_test.py`; guard `sys.exit` in `__main__` |
| P0 | `detect_throttling` double-count untested | Add test: 5 SlowDown lines → `throttle_count == 5` |
| P1 | `parse_lifecycle_xml` prefix overlap untested | Add test: `logs/` + `logs/2024/` → `overlapping_prefixes` flagged |
| P1 | eval --all naming mismatch | Rename example file; add CI eval gate |
| P1 | `analyze_policy` s3:Get* wildcard untested | Add test: policy with `s3:Get*` → allows `s3:GetObject` |
| P1 | `parse_s5cmd_log` has no test at all | Add smoke test case |
| P2 | `analyze_cost` age=0 false positive untested | Add test: no age data → no min_duration_risk warning |
| P2 | Add `ruff check .` to CI | CI catches lint regressions |
| P2 | 4 domains have no golden cases | Add golden cases for `cli_sdk_diagnosis`, `performance_throughput` |
| P3 | `analyze_metadata_amplification` has no test | Add basic smoke test |
