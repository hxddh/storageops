# storageops-eval-golden-cases Scripts

Future scripts for this domain (not yet implemented in v0.1):

## Planned Scripts

### `eval_runner.py`
Run a diagnostic output through one or more golden cases:
- Load golden case(s) from directory.
- Parse expected.json.
- Evaluate output against criteria.
- Compute score and pass/fail per case.
- Check for unsafe output patterns.
- Output structured evaluation report.

Usage:
```bash
./eval_runner.py --case cases/workspace-mount-slow-git/ --output diagnosis.md
./eval_runner.py --all --output-dir diagnoses/
```

### `unsafe_output_scanner.py`
Scan diagnostic output for forbidden patterns:
- Load `unsafe-output-rules.md` patterns.
- Scan output for matches.
- Report matches with line numbers and context.
- Exit non-zero if any match found.

Usage:
```bash
./unsafe_output_scanner.py diagnosis.md
```

### `golden_case_validator.py`
Validate golden case definitions for correctness:
- Check expected.json schema.
- Check that input artifacts exist.
- Check that `must_not_include` is non-empty.
- Check that `expected_min_confidence` is reasonable (0.5–0.95).
- Check that no real secrets are present in input artifacts.

Usage:
```bash
./golden_case_validator.py cases/
```

### `regression_reporter.py`
Compare evaluation results between two runs and report:
- Regressions (previously passing, now failing).
- Improvements (previously failing, now passing).
- Score delta per case.
- Summary statistics.

Usage:
```bash
./regression_reporter.py --baseline eval-baseline.json --current eval-current.json
```

## Principles

- Evaluation must be deterministic (same input → same score).
- Unsafe output detection uses exact/substring matching, not LLM evaluation.
- Keyword matching is case-insensitive.
- Evaluation scripts operate on offline artifacts only.
