# storageops-eval-golden-cases Scripts

Deterministic helpers for StorageOps skill quality gates.

## `golden_case_validator.py`
Validate golden case definitions:
- `expected.json` is valid JSON.
- Required fields exist.
- `expected_min_confidence` is in the supported range.
- `must_not_include` is non-empty.
- `input/` contains artifacts and obvious secrets are not present.

```bash
./golden_case_validator.py ../cases/
./golden_case_validator.py ../cases/workspace-mount-slow-git/ --json
```

## `unsafe_output_scanner.py`
Scan diagnostic output for unsafe recommendations. It uses built-in hard-gate patterns and can also load `expected.must_not_include` from a case.

```bash
./unsafe_output_scanner.py diagnosis.md
./unsafe_output_scanner.py diagnosis.md --case ../cases/adversarial-delete-bucket/
```

## `eval_runner.py`
Compare one diagnostic output against one golden case. The runner checks required keywords, forbidden phrases, and report sections. It emits `PASS`, `SOFT_FAIL`, or `HARD_FAIL`.

```bash
./eval_runner.py --case ../cases/workspace-mount-slow-git/ --output diagnosis.md
```

## `regression_reporter.py`
Compare two JSON result files and report cases that moved from PASS → SOFT_FAIL/HARD_FAIL or disappeared.

```bash
./regression_reporter.py --baseline eval-baseline.json --current eval-current.json
```

## Principles

- Evaluation is deterministic: same input produces the same score.
- Unsafe output detection uses exact/regex matching, not LLM judgment.
- Keyword matching is case-insensitive.
- Scripts operate on offline artifacts only.
