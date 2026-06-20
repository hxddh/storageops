# Lifecycle & Cost Scripts

Deterministic, offline helpers. All output is JSON and expresses cost impact as
structural facts only — minimum-duration DAYS, minimum-billable BYTES, and
amplification MULTIPLIERS. No currency or prices are ever emitted.

## `small_object_analyzer.py`

Flags inventory objects below the per-class minimum billable size and computes
the wasted-bytes penalty and per-object multiplier.

```bash
python3 scripts/small_object_analyzer.py --file <inventory.csv>
```

- Input: CSV with header `key,size_bytes,storage_class` (or `--stdin`).
- Output: `{ok, summary, class_breakdown, recommendations, details}`.
- Canonical minimum-billable-size thresholds live in `_MIN_BILLABLE`
  (STANDARD_IA / ONEZONE_IA / GLACIER_IR = 128 KB, GLACIER / DEEP_ARCHIVE = 40 KB).

## `lifecycle_rule_simulator.py`

Simulates a lifecycle configuration against an object age/size profile and
surfaces structural cost risks deterministically.

```bash
python3 scripts/lifecycle_rule_simulator.py --file <lifecycle.json> \
  --object-age-days <d> --avg-object-size <bytes> [--object-count <n>] \
  [--storage-class STANDARD]
```

- Input: lifecycle config as XML or JSON (e.g. `get-bucket-lifecycle-configuration`
  output) via `--file` or `--stdin`.
- Detects:
  - transitions/expirations applicable at the given age,
  - minimum-duration risk (residency below STANDARD_IA 30 / GLACIER 90 /
    DEEP_ARCHIVE 180 days) reported as `wasted_days`,
  - minimum-billable-size penalty (reuses `small_object_analyzer` thresholds) as
    an amplification `multiplier`,
  - missing `AbortIncompleteMultipartUpload` (orphaned multipart parts),
  - rule conflicts (transition scheduled at/after expiration).
- Output: `{ok, applicable_rules, min_duration_risks, size_penalty, warnings,
  summary, recommendation}`.
- Robust to empty/malformed input: returns `{"ok": false, "error": ...}`, never
  a traceback.

Tests: `tests/test_small_object_analyzer.py`, `tests/test_lifecycle_rule_simulator.py`.
