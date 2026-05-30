# storageops-core Code Review

**Review Date:** 2026-05-30  
**Scope:** `storageops-core/parsers/`, `storageops-core/analyzers/`, `storageops-core/utils/`, `storageops-core/tests/`

---

## 1. Package Structure

```
storageops-core/
├── README.md
├── parsers/
│   ├── parse_awscli_debug.py
│   ├── parse_lifecycle_xml.py
│   ├── parse_rclone_log.py
│   ├── parse_s5cmd_error.py
│   ├── parse_s5cmd_log.py
│   └── parse_sigv4_error.py
├── analyzers/
│   ├── analyze_cost.py
│   ├── analyze_metadata_amplification.py
│   ├── analyze_policy.py
│   ├── analyze_throughput.py
│   ├── detect_throttling.py
│   └── eval_runner.py
├── utils/
│   └── secret_scanner.py
└── tests/
    └── smoke_test.py
```

**Missing:** No `__init__.py` in any directory. No `pyproject.toml`. Cannot be `pip install`-ed as a standalone package.

---

## 2. Parser Review

### 2.1 parse_awscli_debug.py

**Verified facts:**
- Correctly parses `DEBUG` prefixed log lines from `aws --debug` output
- Extracts HTTP method, URL, status code, response body (truncated at 500 chars)
- Extracts credential source from `Found credentials in...` pattern
- Detects `SignatureDoesNotMatch`, `InvalidAccessKeyId`, `ExpiredToken`, `AccessDenied` from response XML

**Bugs:**
- `lines = text.split('\n')` at line ~61 — **dead code** (ruff F841). The variable is never used. The actual iteration is done via `for line in text.splitlines()` elsewhere.
- Credential source extraction is additive (appends to a list on every match) with no deduplication. If the same credential source line appears multiple times in a debug log, it is recorded multiple times.

**Gaps:**
- No input size limit. A 100MB debug log file would be processed in memory without truncation.
- The `error` pattern (`ERROR|FAIL|Exception|Traceback`) is broad — may capture structured JSON error payloads in response bodies that are not actual errors.

**Correctness:** Otherwise sound. Patterns are specific enough to avoid most false positives.

---

### 2.2 parse_rclone_log.py

**Verified facts:**
- Correctly classifies ETags: `{12,}` hex minimum correctly accepts 32-char MD5 (`single_put_md5`) and 33+ char multipart (`multipart_etag_format`)
- MD5 source/dest patterns use `re.IGNORECASE` — handles mixed-case log output correctly
- Timeout detection fires on `context deadline exceeded` and `connection timed out`

**Bug:**
- `timeout_error` and `failed_copy` patterns can match the same line. A timeout that causes a copy failure is added to both `failed` list AND `timeouts` list. Then `failed_count = len(failed_items)` includes the timeout-failures, while `timeout_count = len(timeouts)` also counts them. The caller in `detect_throttling` may double-count these. **Severity: P2** — inflates failure counts in combined analysis.

**Gaps:**
- No detection of `--checksum` vs `--size-only` sync mode from log output — relevant for diagnosing corrupted transfers
- No parsing of `rclone config` dump in debug logs (credential extraction)

---

### 2.3 parse_sigv4_error.py

**Verified facts:**
- `h = lambda ...` (ruff E731 violation) — functions correctly; walrus operator returns `None` for absent XML tags, outer `or ""` converts to empty string. No functional impact.
- `diagnose()` only performs clock_skew check when `system_time` argument is provided. Called with no args in smoke_test, so clock_skew check is always skipped in the smoke test.

**Gap:**
- The `canonical_request` and `string_to_sign` extracted from error XML are stored in output but not validated against any expected format. A truncated or malformed SigV4 error response would produce empty fields silently.

**Correctness:** Sound for well-formed SigV4 error responses.

---

### 2.4 parse_lifecycle_xml.py

**Verified facts:**
- Parses AWS S3 lifecycle XML format correctly for transitions, expirations, filters
- Flags `STANDARD_IA` transitions without size filter (correct, important cost guard)
- `break` in the STANDARD_IA warning loop prevents duplicate warnings per rule — correct

**Bug (P1 — logic correctness):**
- **Hierarchical prefix overlap not detected.** The overlap check is:
  ```python
  if len(prefixes) != len(set(prefixes)):
      warnings.append("overlapping_prefixes")
  ```
  This only catches **exact duplicate** prefixes. `logs/` and `logs/2024/` both match `logs/2024/` objects but are NOT flagged as overlapping. This can cause users to unknowingly apply two lifecycle rules to the same objects, leading to unexpected deletions or transitions.

**Recommendation:**
```python
# Check if any prefix is a prefix of another prefix
sorted_prefixes = sorted(prefixes)
for i in range(len(sorted_prefixes) - 1):
    if sorted_prefixes[i+1].startswith(sorted_prefixes[i]):
        warnings.append("overlapping_prefixes")
        break
```

---

### 2.5 parse_s5cmd_error.py and parse_s5cmd_log.py

**Status:** These parsers exist and compile correctly. `parse_s5cmd_log.py` is used in `cmd_analyze()` for `performance_throughput`. Neither is invoked by `agent.py`'s `run_analysis()`.

**No functional bugs identified** in the parsers themselves. The gap is at the wiring layer (agent not using them).

---

## 3. Analyzer Review

### 3.1 detect_throttling.py

**Bug (P0 — verified):**
Double-counting `SlowDown` errors. The analyzer tracks:
1. `status_codes[429]` — HTTP 429 responses
2. `slowdown_count` — lines matching exact string `SlowDown`
3. `throttle_errors` — lines matching broader pattern `(ThrottlingException|SlowDown|RequestLimitExceeded|...)`

`SlowDown` matches pattern (2) AND pattern (3). For a log with 5 `SlowDown` lines:
- `slowdown_count = 5`
- `throttle_errors` also increments by 5 for the same lines
- `throttle_count = status_codes[429] + slowdown_count + throttle_errors = 0 + 5 + 5 = 10`

**Actual correct count should be 5.** This inflates `throttle_rate_percent` by up to 2×.

**Fix:** Use mutually exclusive counters. Either count `SlowDown` only in `throttle_errors` (and remove `slowdown_count`) or exclude `SlowDown` from the broader `throttle_errors` pattern.

---

### 3.2 analyze_policy.py

**Verified facts:**
- `_find_action_match()` handles `s3:*` and `*` wildcards correctly
- `_find_resource_match()` handles `/*` suffix wildcard correctly for bucket ARNs
- `analyze_inline_403()` fallback path is clearly marked with caveats

**Bug (P1):**
`_find_action_match()` does NOT handle prefix wildcards like `s3:Get*`. A policy with `Action: ["s3:Get*"]` would NOT match a check for `s3:GetObject`. This is a common IAM policy pattern.

**Evidence:** The comment in the code explicitly says prefix matching is not implemented. This is a known gap, not an unknown bug.

**Impact:** A policy with `"Action": "s3:Get*"` would be analyzed as "action not allowed" even though it permits `s3:GetObject`. This produces false-positive denial diagnoses.

**Fix:**
```python
# In _find_action_match():
if action_in_policy.endswith('*'):
    prefix = action_in_policy[:-1]
    if requested_action.startswith(prefix):
        return True
```

---

### 3.3 analyze_cost.py

**Verified facts:**
- Division-by-zero protection: `penalty_multiplier = billable_gb / actual_gb if actual_gb > 0 else 0` — safe
- GLACIER `MIN_BILLABLE_SIZE_KB: 0` is correctly distinguished from the 40KB overhead

**Bug (P1):**
`avg_object_age_days` defaults to `0` when not provided. The minimum-duration check fires when `avg_object_age_days < 30` (for IA) or `< 90` (for Glacier). `0 < 30` is always true, so **every cost analysis without age data flags a minimum duration risk.**

This produces false positives for users who have not provided age data and whose objects are actually older than 30/90 days.

**Fix:** Add a sentinel value:
```python
avg_object_age_days = data.get('avg_object_age_days', None)
if avg_object_age_days is not None and avg_object_age_days < 30:
    warnings.append("minimum_duration_risk")
```

---

### 3.4 analyze_throughput.py

**No functional bugs identified.** The throughput model is reasonable — it calculates expected vs observed throughput and flags outliers.

**Gap:** No differentiation between same-region and cross-region throughput expectations. A 50 MB/s observation might be normal for cross-region but slow for same-region.

---

### 3.5 analyze_metadata_amplification.py

**No functional bugs identified.**

**Gap:** The amplification calculation assumes uniform object size distribution. For bimodal distributions (many tiny + few large objects), the amplification estimate can be off by an order of magnitude.

---

### 3.6 eval_runner.py

**Verified facts:**
- `sys` imported but unused (ruff F401) — minor
- Hard gates (`category_match`, `unsafe_output`) have weight `0.0` but are evaluated separately. A report can score high on weighted criteria even if it fails a hard gate — the final score correctly reflects this as separate `score` and `hard_gate_passed` fields.

**Bug (P2):**
`scan_unsafe()` context-skip logic uses:
```python
if 'analysis' in context_window:
    continue  # skip this finding
```
This suppresses unsafe pattern matches when the word "analysis" appears anywhere in the surrounding 5 lines. This is too broad — the word "analysis" is common in diagnostic output and would suppress legitimate unsafe content.

**Bug (P2):**
`--no-sign-request` in a `# manual-only:` prefixed code block triggers the `disable_auth` unsafe pattern. The `scan_unsafe()` function does not check for `manual-only:` prefix before flagging. A correctly-formatted SKILL.md validation command section fails the eval gate.

**Recommendation:** Check for `manual-only:` prefix (or any comment prefix) before flagging unsafe patterns in code blocks.

---

## 4. secret_scanner.py Review

**Verified facts:**
- 11 regex patterns covering AWS, Baidu Cloud, JWT, pre-signed URLs, rclone config credentials
- Safe placeholder allowlist: `YOUR_ACCESS_KEY`, `YOUR_SECRET_KEY`, `<your-key>`, `<placeholder>`, `[REDACTED]`
- `lines = text.split('\n')` dead code at line ~103 (ruff F841)
- O(n²) redaction algorithm — functionally correct but slow for logs with many secrets

**Coverage gaps (P1):**
- **Alibaba Cloud:** Access key format: `LTAI` prefix + 16-24 alphanum chars — not covered
- **Tencent Cloud:** Secret ID format: `AKID` prefix + 32 alphanum chars — not covered
- **Google Cloud:** Service account JSON `"private_key_id"` and `"private_key"` fields — not covered
- **Azure:** SAS token `sig=` parameter in URLs — not covered
- **Huawei Cloud:** `AK: [A-Z0-9]{20}` format — not covered

**Potential false positive (P3):**
The `bcecmd` pattern `(ak|sk)\s*=\s*\S+` would match `task = value` only if the line literally starts with `ak` or `sk`. In practice, `ak` and `sk` are short common strings in non-credential contexts (e.g., `stack = ...`). The risk is low but non-zero.

**Correctness for covered patterns:** Sound. Reverse-order processing of findings ensures that redacting a value at a later position does not shift offsets for earlier positions.

---

## 5. Tests Review

### 5.1 smoke_test.py

**Critical bug (P0):**
`sys.exit(0)` is called at module level (final line of the script). When pytest imports `smoke_test.py` as a test module, it immediately exits the Python process with `INTERNALERROR`. **pytest cannot run any tests in this file.**

**Evidence:** `pytest -q` output:
```
INTERNALERROR> SystemExit: 0
```

**Fix:**
1. Wrap the `sys.exit(0)` in `if __name__ == '__main__': sys.exit(0)`
2. Rename test functions from `def check_X():` to `def test_X():`
3. Add `import pytest` and use `pytest.fail()` instead of `print("FAIL")`

**Coverage:**
- 7 test cases covering: AKIA detection, safe placeholders, rclone ETag mismatch, SigV4 parsing, policy analysis, cost analysis, awscli parsing
- Missing coverage: `parse_lifecycle_xml`, `analyze_throughput`, `analyze_metadata_amplification`, `eval_runner`, `detect_throttling`

---

## 6. Summary Table

| Module | Bugs | Gaps | Severity |
|---|---|---|---|
| `parse_awscli_debug.py` | Dead code `lines` | No size limit | P3 |
| `parse_rclone_log.py` | Double-count timeout+failed | No sync mode detection | P2 |
| `parse_sigv4_error.py` | clock_skew never checked in smoke test | — | P3 |
| `parse_lifecycle_xml.py` | Hierarchical prefix overlap not detected | — | P1 |
| `detect_throttling.py` | SlowDown double-counted (throttle_rate inflated) | — | P0 |
| `analyze_policy.py` | `s3:Get*` wildcard not handled | SCP not covered | P1 |
| `analyze_cost.py` | age=0 false positive min-duration warning | Cross-region cost | P1 |
| `analyze_throughput.py` | — | Same vs cross-region baseline | P3 |
| `eval_runner.py` | Unsafe gate false positive for manual-only | context-skip too broad | P2 |
| `secret_scanner.py` | Dead code `lines` | Alibaba/Tencent/GCP/Azure | P1 |
| `smoke_test.py` | `sys.exit(0)` breaks pytest | Missing 5 module coverages | P0 |
