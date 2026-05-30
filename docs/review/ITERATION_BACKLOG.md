# Iteration Backlog

**Review Date:** 2026-05-30  
**Format:** SO-NNN, Priority P0–P3, evidence-backed

---

# Issue ID: SO-001

## Title
Fix pytest crash caused by `sys.exit(0)` at module level in smoke_test.py

## Priority
P0

## Area
Test

## Problem
`storageops-core/tests/smoke_test.py` calls `sys.exit(0)` at the module level (final statement of the file). When pytest imports this file during test collection, the Python process immediately terminates. `pytest -q` produces `INTERNALERROR> SystemExit: 0` and runs zero tests.

## Evidence
- File: `storageops-core/tests/smoke_test.py`, last line: `sys.exit(0 if all_passed else 1)` at module level (not inside `__main__` guard)
- Command: `pytest -q` → `INTERNALERROR> SystemExit: 0`
- Functions named `check_X()` instead of `test_X()` — pytest would not collect even without the sys.exit issue

## Expected Outcome
Running `pytest -q storageops-core/tests/smoke_test.py` collects and runs 7+ test functions, all passing.

## Suggested Implementation
1. Guard `sys.exit()` call: `if __name__ == '__main__': sys.exit(0 if all_passed else 1)`
2. Rename all `check_X()` → `test_X()` for pytest collection
3. Replace `print("FAIL: ...")` with `assert False, "..."` or `pytest.fail("...")`
4. Add `pytest` to `pyproject.toml` dev dependencies
5. Add `[tool.pytest.ini_options]` section to `pyproject.toml` with `testpaths = ["storageops-core/tests"]`

## Acceptance Criteria
- `pytest -q` exits 0
- All 7 existing test cases pass
- No INTERNALERROR

## Test Plan
Run `pytest -q` before and after. CI step runs `pytest -q` and fails on non-zero exit.

## Risk
None — this is a test infrastructure fix with no production code changes.

---

# Issue ID: SO-002

## Title
Fix double-counting bug in detect_throttling.py inflating throttle_rate_percent

## Priority
P0

## Area
Core

## Problem
`SlowDown` errors are counted twice: once in `slowdown_count` (exact match) and once in `throttle_errors` (broad pattern match that includes `SlowDown`). The final `throttle_count = status_codes[429] + slowdown_count + throttle_errors` therefore includes `SlowDown` errors twice.

## Evidence
- File: `storageops-core/analyzers/detect_throttling.py`
- Both `slowdown_count` (exact `SlowDown` match) and `throttle_errors` (broad `ThrottlingException|SlowDown|...` match) fire on the same lines
- For 10 `SlowDown` lines: `throttle_count` = 0+10+10 = 20 instead of correct 10
- This inflates `throttle_rate_percent` by up to 2× for `SlowDown`-heavy logs

## Expected Outcome
`throttle_count` for a log with N `SlowDown` errors and M HTTP 429 errors = N + M (no double-counting). `throttle_rate_percent` is accurate.

## Suggested Implementation
Remove `slowdown_count` as a separate counter. Include `SlowDown` only in `throttle_errors`. Alternatively, exclude `SlowDown` from the `throttle_errors` broad pattern and keep the separate counter, but use `max(slowdown_count, in_throttle_errors)` in the final sum.

Simplest fix:
```python
# Remove separate slowdown_count
# Ensure throttle_errors pattern covers SlowDown
throttle_count = status_codes.get(429, 0) + status_codes.get('429', 0) + throttle_errors
```

## Acceptance Criteria
- New test: 5 `SlowDown` lines → `throttle_count == 5`, `throttle_rate_percent == 5/total * 100`
- Existing smoke tests still pass

## Test Plan
Add to `smoke_test.py`:
```python
def test_throttling_no_double_count():
    text = "\n".join(["SlowDown: reduce your request rate"] * 5)
    result = detect_throttling(text, total_requests=100)
    assert result['throttle_count'] == 5
```

## Risk
Low. Fix is isolated to counter arithmetic in one function.

---

# Issue ID: SO-003

## Title
Fix storageops eval --all always reporting failures (filename mismatch)

## Priority
P0

## Area
CLI/Eval

## Problem
`storageops eval --all` matches output files against golden case IDs by exact filename. The only example file is named `end-to-end-rclone-corrupted-transfer.md` but the golden case ID is `rclone-corrupted-transfer`. Every eval run reports 5/5 cases failed.

## Evidence
- Golden case directory: `agents/skills/storageops-eval-golden-cases/cases/rclone-corrupted-transfer/`
- Example file: `docs/examples/end-to-end-rclone-corrupted-transfer.md`
- `eval_runner.py`: matches by `case_id` exact match against filename stem

## Expected Outcome
`storageops eval --all docs/examples/` finds the rclone-corrupted-transfer example, scores it against `expected.json`, and reports 1/5 with real score (rest skipped as no output found).

## Suggested Implementation
Option A (simpler): Rename `docs/examples/end-to-end-rclone-corrupted-transfer.md` → `docs/examples/rclone-corrupted-transfer.md`

Option B (more robust): In `cmd_eval()`, normalize filename stems: strip common prefixes like `end-to-end-`, `case-`, `example-` before matching against case IDs. Or match by substring (`case_id in filename_stem`).

## Acceptance Criteria
- `storageops eval --all docs/examples/` finds and scores at least 1 case successfully
- Score for the rclone case is ≥ 0.7 (it was 1.0 when tested manually)

## Test Plan
Add CI step: `storageops eval rclone-corrupted-transfer docs/examples/rclone-corrupted-transfer.md` exits 0 with score ≥ 0.7.

## Risk
Low. Renaming one file has no production impact.

---

# Issue ID: SO-004

## Title
Fix hierarchical prefix overlap detection in parse_lifecycle_xml.py

## Priority
P1

## Area
Core

## Problem
The lifecycle parser only detects exact-duplicate prefixes. Hierarchical overlaps like `logs/` and `logs/2024/` are not detected, even though both rules would apply to `logs/2024/file.txt`, potentially causing unexpected double-transitions or premature deletions.

## Evidence
- File: `storageops-core/parsers/parse_lifecycle_xml.py`
- Check: `len(prefixes) != len(set(prefixes))` — only catches exact duplicates
- Hierarchical overlap `logs/` + `logs/2024/` → set has 2 unique values → NOT flagged

## Expected Outcome
A lifecycle config with `logs/` and `logs/2024/` prefixes raises `overlapping_prefixes` warning.

## Suggested Implementation
```python
sorted_pfx = sorted(p for p in prefixes if p)  # empty prefix = applies to all
for i in range(len(sorted_pfx) - 1):
    if sorted_pfx[i+1].startswith(sorted_pfx[i]):
        warnings.append("overlapping_prefixes")
        break
# Also check for empty prefix (applies to all objects) with any other prefix
if '' in prefixes and len(prefixes) > 1:
    warnings.append("overlapping_prefixes")
```

## Acceptance Criteria
- `logs/` + `logs/2024/` → `overlapping_prefixes` in warnings
- `images/` + `videos/` → no overlap warning
- Empty prefix + any other prefix → overlap warning
- Exact duplicate `logs/` + `logs/` → overlap warning (existing behavior preserved)

## Test Plan
Add parametrized pytest cases for each scenario above.

## Risk
Low. Parser change only. No CLI behavior change.

---

# Issue ID: SO-005

## Title
Fix false-positive minimum-duration cost warning when avg_object_age_days is absent

## Priority
P1

## Area
Core

## Problem
`analyze_cost.py` defaults `avg_object_age_days` to `0` when not provided in input. Since `0 < 30` (IA minimum) is always true, every cost analysis that omits age data warns about minimum duration risk, regardless of actual object age.

## Evidence
- File: `storageops-core/analyzers/analyze_cost.py`
- Code: `avg_object_age_days = data.get('avg_object_age_days', 0)` → always flags IA/Glacier objects when age not provided
- Smoke test passes because the test provides explicit age data, masking this bug

## Expected Outcome
When `avg_object_age_days` is not provided, no minimum duration warning is generated. Warning only fires when age data is present AND shows objects younger than the storage class minimum.

## Suggested Implementation
```python
avg_object_age_days = data.get('avg_object_age_days', None)
if avg_object_age_days is not None:
    if storage_class in ('STANDARD_IA', 'ONEZONE_IA') and avg_object_age_days < 30:
        warnings.append("minimum_duration_risk")
    elif storage_class.startswith('GLACIER') and avg_object_age_days < 90:
        warnings.append("minimum_duration_risk")
```

## Acceptance Criteria
- `analyze_cost({storage_class: STANDARD_IA})` (no age) → no `minimum_duration_risk`
- `analyze_cost({storage_class: STANDARD_IA, avg_object_age_days: 10})` → `minimum_duration_risk` present
- `analyze_cost({storage_class: STANDARD_IA, avg_object_age_days: 60})` → no `minimum_duration_risk`

## Test Plan
Add 3 parametrized test cases. Update smoke test to cover the no-age case.

## Risk
Low. False positives become true negatives. No false negatives introduced.

---

# Issue ID: SO-006

## Title
Add s3:Get* and s3:Put* prefix wildcard support to analyze_policy.py

## Priority
P1

## Area
Core

## Problem
`analyze_policy._find_action_match()` handles `s3:*` and `*` wildcards but NOT prefix wildcards like `s3:Get*`. A policy with `Action: ["s3:Get*"]` is analyzed as not allowing `s3:GetObject`, producing a false-positive access denial diagnosis.

## Evidence
- File: `storageops-core/analyzers/analyze_policy.py`, `_find_action_match()` function
- Comment in code explicitly states prefix matching is not implemented
- Common IAM policy pattern: `"Action": ["s3:Get*", "s3:List*"]`

## Expected Outcome
`_find_action_match("s3:Get*", "s3:GetObject")` returns `True`. All standard AWS wildcard patterns are handled.

## Suggested Implementation
```python
def _find_action_match(action_in_policy: str, requested_action: str) -> bool:
    if action_in_policy in ('*', 's3:*'):
        return True
    if action_in_policy == requested_action:
        return True
    if action_in_policy.endswith('*'):
        prefix = action_in_policy[:-1]
        if requested_action.startswith(prefix):
            return True
    return False
```

## Acceptance Criteria
- `s3:Get*` matches `s3:GetObject`, `s3:GetObjectAcl`, `s3:GetBucketLocation`
- `s3:Get*` does NOT match `s3:PutObject`
- `s3:*` still matches everything
- `*` still matches everything

## Test Plan
Add parametrized test covering: exact match, prefix wildcard match, prefix wildcard non-match, full wildcard.

## Risk
Low. Increases true-positive rate; no new false positives expected from stricter matching.

---

# Issue ID: SO-007

## Title
Convert storageops-core to a proper installable Python package

## Priority
P1

## Area
Packaging

## Problem
`storageops-core/parsers/`, `analyzers/`, and `utils/` have no `__init__.py` and no `pyproject.toml`. All imports rely on `sys.path` mutation. This makes `storageops-core` impossible to install independently, breaks IDE tooling, and requires every consumer to replicate the path hack.

## Evidence
- No `__init__.py` files in `storageops-core/` subtrees (confirmed by file tree)
- `storageops-cli/storageops/cli.py` lines 5-10: manual `sys.path.insert(0, ...)` calls
- `storageops-cli/pyproject.toml`: `dependencies = []` — core not listed as dependency

## Expected Outcome
`pip install -e storageops-core/` succeeds. `from storageops_core.parsers.parse_rclone_log import parse` works without any `sys.path` manipulation.

## Suggested Implementation
1. Add `storageops-core/__init__.py` (empty)
2. Add `storageops-core/parsers/__init__.py` (empty)
3. Add `storageops-core/analyzers/__init__.py` (empty)
4. Add `storageops-core/utils/__init__.py` (empty)
5. Add `storageops-core/pyproject.toml`:
   ```toml
   [project]
   name = "storageops-core"
   version = "0.1.0"
   requires-python = ">=3.9"
   dependencies = []
   ```
6. Update `storageops-cli/pyproject.toml` to add `"storageops-core"` to dependencies
7. Remove `sys.path` manipulation from `cli.py`, `agent.py`, `run_validation.py`, `smoke_test.py`

## Acceptance Criteria
- `pip install -e storageops-core/` exits 0
- `from storageops_core.parsers.parse_rclone_log import parse` works in a fresh Python session
- All existing tests still pass
- No `sys.path.insert` calls remain in production code

## Test Plan
Add CI step: `pip install -e storageops-core/ && python -c "from storageops_core.parsers.parse_rclone_log import parse; print('OK')"`.

## Risk
Medium. Requires updating all import paths. Need to verify no circular imports.

---

# Issue ID: SO-008

## Title
Add Alibaba Cloud and Tencent Cloud credential patterns to secret_scanner.py

## Priority
P1

## Area
Security

## Problem
`secret_scanner.py` covers AWS and Baidu Cloud credentials but not Alibaba Cloud (`LTAI` prefix) or Tencent Cloud (`AKID` prefix). Users of these platforms who analyze logs containing credentials would have them transmitted un-redacted.

## Evidence
- File: `storageops-core/utils/secret_scanner.py`: 11 patterns, none matching `LTAI` or `AKID` prefixes
- Target user base implied by Baidu Cloud coverage: Chinese cloud market — Alibaba and Tencent are the two largest providers in this market

## Expected Outcome
Alibaba and Tencent Cloud access keys are detected and redacted with the same reliability as AWS access keys.

## Suggested Implementation
```python
# Alibaba Cloud Access Key ID: LTAI prefix + 16-24 alphanumeric chars
(r'LTAI' + r'[A-Za-z0-9]{16,24}', 'alibaba_access_key_id'),
# Tencent Cloud Access Key ID: AKID prefix + 32 alphanumeric chars
(r'AKID' + r'[A-Za-z0-9]{32}', 'tencent_access_key_id'),
# Alibaba Cloud secret (appears as AccessKeySecret in SDKs)
(r'(?:AccessKeySecret|aliyun_secret)["\s]*[:=]["\s]*([A-Za-z0-9]{30})', 'alibaba_secret'),
```

## Acceptance Criteria
- `LTAI4GF<20-char-alphanum>` (Alibaba Cloud key format) → detected and redacted
- `AKID<32-char-alphanum>` (Tencent Cloud key format) → detected and redacted
- Safe placeholder `YOUR_ALIBABA_KEY` → NOT flagged

## Test Plan
Add 2 new test cases to `smoke_test.py`:
- `test_secret_scanner_detects_alibaba_key()`
- `test_secret_scanner_detects_tencent_key()`

## Risk
Low. Additive change to scanner. New false positive risk is low given the distinctive `LTAI`/`AKID` prefixes.

---

# Issue ID: SO-009

## Title
Add security warning to --no-redact CLI flag

## Priority
P1

## Area
Security / CLI

## Problem
`storageops report --no-redact` and `storageops analyze --no-redact` bypass all secret redaction. No warning is displayed. A user could inadvertently share output containing raw AWS access keys, session tokens, or Authorization headers.

## Evidence
- File: `storageops-cli/storageops/cli.py:429`
- Flag registered as `help="disable secret redaction"` with no stderr warning on activation
- The flag exists for legitimate debugging use but is too easy to misuse silently

## Expected Outcome
When `--no-redact` is used, a prominent warning is printed to stderr before any output is produced.

## Suggested Implementation
In `cmd_report()` and `cmd_analyze()`, before processing:
```python
if args.no_redact:
    print(
        "WARNING: --no-redact is active. Output may contain raw credentials. "
        "Do not share, log, or store this output without manual review.",
        file=sys.stderr
    )
```

## Acceptance Criteria
- `storageops report --no-redact` prints warning to stderr before report output
- Warning appears on stderr (not stdout), so it doesn't corrupt JSON/Markdown output
- `storageops report` without `--no-redact` prints no warning

## Test Plan
Capture stderr in test and assert warning string is present when `--no-redact` used.

## Risk
None. Warning-only change, no behavior change.

---

# Issue ID: SO-010

## Title
Add `ruff check .` and `pytest -q` to CI workflow

## Priority
P1

## Area
CI

## Problem
CI currently runs `smoke_test.py` and `run_validation.py` directly as scripts but does NOT run `pytest` or `ruff`. There are currently 24 ruff violations that CI does not catch. Once SO-001 (pytest fix) is done, CI still won't run pytest unless the workflow is updated.

## Evidence
- File: `.github/workflows/ci.yml` — no `ruff check .` step, no `pytest` step
- `ruff check .` currently exits non-zero (24 violations)

## Expected Outcome
CI runs `ruff check .` and `pytest -q` on every push. Failures block merge.

## Suggested Implementation
Add to `.github/workflows/ci.yml` after install step:
```yaml
- name: Lint
  run: ruff check .
- name: Test
  run: pytest -q
```

Also add `ruff` and `pytest` to dev dependencies in `pyproject.toml`:
```toml
[project.optional-dependencies]
dev = ["ruff", "pytest"]
```

## Acceptance Criteria
- CI fails if `ruff check .` exits non-zero
- CI fails if `pytest -q` exits non-zero
- All existing violations fixed before adding lint gate (or add `--fix` pass first)

## Test Plan
Push a branch with a deliberate ruff violation; verify CI fails.

## Risk
Medium — requires fixing 24 existing ruff violations before adding lint gate, otherwise CI immediately breaks. Sequence: fix violations first (SO-011), then add CI gate.

---

# Issue ID: SO-011

## Title
Fix all 24 ruff lint violations

## Priority
P2

## Area
Core / CLI

## Problem
`ruff check .` reports 24 violations across `smoke_test.py`, `agent.py`, `run_validation.py`, parsers, and analyzers. These include unused variables (F841), unused imports (F401), f-strings without placeholders (F541), and a lambda assignment (E731). 8 are auto-fixable.

## Evidence
- `ruff check .` output: 24 violations
- F841 (6): `lines` in `parse_awscli_debug.py` and `secret_scanner.py`; `helpful`, `found_count`, `has_config`, `has_timing`, `has_tool` in `agent.py`
- F401 (3): `sys` in `eval_runner.py`; `json` and `diagnose` in `smoke_test.py`
- F541 (4): f-strings without placeholders in `agent.py` and `run_validation.py`
- E402 (8): imports after sys.path manipulation — intentional, suppress with `# noqa: E402`
- E731 (1): lambda in `parse_sigv4_error.py`
- F841 `found_count` in `agent.py` is dead code (see SO-012)

## Expected Outcome
`ruff check .` exits 0.

## Suggested Implementation
1. Run `ruff check --fix .` for auto-fixable violations
2. Manually fix remaining: remove dead variables, add `# noqa: E402` to intentional path-manipulation imports, convert lambda to `def`
3. Add `[tool.ruff]` section to `pyproject.toml` with appropriate ignore rules for intentional patterns

## Acceptance Criteria
- `ruff check .` exits 0
- No functionality changes

## Test Plan
Run `ruff check .` before and after. Run smoke tests to verify no behavior change.

## Risk
Low. Mostly cosmetic changes plus dead code removal.

---

# Issue ID: SO-012

## Title
Remove dead variables and simplify classify_evidence() in agent.py

## Priority
P2

## Area
Agent

## Problem
`classify_evidence()` in `agent.py` always returns `evidence_quality: 'partial'` because `found_count` is never incremented. 5 variables (`helpful`, `found_count`, `has_config`, `has_timing`, `has_tool`) are assigned but never read. The function body is misleading dead code.

## Evidence
- File: `storageops-cli/storageops/agent.py`
- `found_count = 0` set at line ~182, never incremented, condition `if found_count >= 3` is always false
- Comment: "# Simplified: we assume partial until interactive"
- Variables `has_config`, `has_timing`, `has_tool` assigned in `assess_evidence()` but never read

## Expected Outcome
`classify_evidence()` is either (a) simplified to `return 'partial'` with a `# TODO: implement with LLM-based evidence assessment` comment, or (b) properly implemented to count evidence items.

## Suggested Implementation
For now (v0.1 scope):
```python
def classify_evidence(text: str, domain: str) -> str:
    # TODO(SO-012): Implement evidence-quality scoring with LLM assistance
    return 'partial'
```
Remove the 5 dead variables.

## Acceptance Criteria
- `ruff check .` passes (F841 violations removed)
- `storageops agent` behavior unchanged (it uses `assess_evidence()` not `classify_evidence()` for the quality gate)

## Test Plan
Run existing smoke tests and validation. Verify no behavior change.

## Risk
None. Dead code removal only.

---

# Issue ID: SO-013

## Title
Implement network_endpoint_access analyzer

## Priority
P1

## Area
Core / CLI

## Problem
The `network_endpoint_access` domain returns a stub response from `cmd_analyze()` with no actual analysis. The `storageops-network-endpoint-access` Skill has a full SKILL.md and 5 reference documents but no corresponding analyzer in `storageops-core/analyzers/`.

## Evidence
- `storageops-cli/storageops/cli.py`: network domain branch returns hardcoded stub
- No `analyze_network_endpoint.py` in `storageops-core/analyzers/`
- Full reference set exists: `dns-host-header.md`, `endpoint-routing.md`, `private-access.md`, `tls-mtu-rtt.md`, `cross-cloud-dedicated-line.md`

## Expected Outcome
`storageops analyze --domain network_endpoint_access --input <log>` performs real analysis of: DNS resolution failures, endpoint routing errors, TLS errors, connectivity issues.

## Suggested Implementation
Create `storageops-core/analyzers/analyze_network_endpoint.py` covering:
- DNS resolution failure patterns (`NXDOMAIN`, `connection refused`, `no such host`)
- Endpoint style detection (`virtual-hosted-style` vs `path-style`)
- TLS errors (`certificate verify failed`, `SSL: WRONG_VERSION_NUMBER`)
- MTU-related issues (fragmentation, small packet RTT anomalies)
- Private endpoint vs public endpoint routing signals

Create matching parser `storageops-core/parsers/parse_network_log.py` for common connectivity tool outputs (curl verbose, dig, traceroute).

## Acceptance Criteria
- `storageops analyze --domain network_endpoint_access` returns structured JSON with real findings
- At least 3 golden test cases for DNS failure, TLS error, endpoint routing mismatch
- Smoke test case added

## Test Plan
Add 3 cases to `tests/validation/inputs/` and corresponding golden cases.

## Risk
Medium — requires research into common network tool output formats. References exist in the Skill Pack.

---

# Issue ID: SO-014

## Title
Write SECURITY.md and CONTRIBUTING.md

## Priority
P1

## Area
Docs

## Problem
The repository has no `SECURITY.md` (security model documentation) and no `CONTRIBUTING.md` (developer onboarding). These are missing for a project claiming enterprise-readiness.

## Evidence
- `ls /home/user/storageops/` — no `SECURITY.md`, no `CONTRIBUTING.md`

## Expected Outcome
- `SECURITY.md`: documents the security model (offline-only, no cloud ops, redaction-by-default, manual-only command policy, how to report vulnerabilities)
- `CONTRIBUTING.md`: documents development setup, coding conventions, how to add a new Skill, how to add a new parser/analyzer, testing conventions, PR process

## Suggested Implementation
Write both documents based on patterns observed in this review. See `DOCUMENTATION_REVIEW.md` for required content.

## Acceptance Criteria
- `SECURITY.md` explains: what the tool does and doesn't do, the redaction guarantee, the no-cloud-ops guarantee, and how to report a vulnerability
- `CONTRIBUTING.md` explains: how to run tests locally, how to add a Skill, how to add a parser, coding style (ruff), PR checklist

## Test Plan
Review by a developer unfamiliar with the codebase.

## Risk
None. Documentation only.

---

# Issue ID: SO-015

## Title
Fix scan_unsafe() false positive for manual-only prefixed commands

## Priority
P2

## Area
Security / Eval

## Problem
`eval_runner.py`'s `scan_unsafe()` flags `--no-sign-request` as unsafe even when it appears in a `# manual-only:` prefixed code block. This means a correctly-formatted SKILL.md verification section would fail the eval gate.

## Evidence
- File: `storageops-core/analyzers/eval_runner.py`, `scan_unsafe()` function
- Pattern `--no-sign-request` matches the `disable_auth` unsafe pattern
- SKILL.md files include `# manual-only: aws s3 ls s3://bucket/ --no-sign-request` as valid diagnostic commands
- Context-skip checks for word "analysis" but not for `manual-only:` prefix

## Expected Outcome
Commands preceded by `# manual-only:` are not flagged as unsafe output.

## Suggested Implementation
```python
line = lines[i]
# Skip if line is a manual-only annotation
if line.strip().startswith('# manual-only:') or '# manual-only:' in line:
    continue
for pattern_name, pattern in UNSAFE_PATTERNS.items():
    if re.search(pattern, line, re.IGNORECASE):
        findings.append(...)
```

## Acceptance Criteria
- `# manual-only: aws s3 ls s3://bucket/ --no-sign-request` → not flagged
- `aws s3 ls s3://bucket/ --no-sign-request` (without prefix) → still flagged
- Add test case with manual-only annotated command

## Test Plan
Add test to smoke_test.py or eval test suite.

## Risk
Low. Additive exception to existing check.
