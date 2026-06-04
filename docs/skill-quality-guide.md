# Skill Quality Guide

StorageOps skills are runtime instructions. They should be concise, testable, and safe.

## Required Shape

Every `skills/storageops-*/SKILL.md` should contain:

- YAML frontmatter with `name`, `description`, `maturity`, `mode`, `trigger_keywords`, and `recommended_tools`.
- A decision tree or routing checklist.
- Evidence requirements.
- A workflow with clear stopping points.
- User interaction guidance.
- An output contract, not a rigid exact template.
- References with `Read when:` guidance.

## Quality Principles

- Keep `SKILL.md` operational. Move detailed provider notes into `references/`.
- Keep volatile facts out of `SKILL.md`. Put prices, provider version behavior,
  and dated service assumptions in references with a verification date.
- Tool and SDK references must declare scope and verification steps. Do not
  apply a CLI config path, SDK credential chain, or provider default to another
  tool unless the reference names that compatibility explicitly.
- Use deterministic scripts for parsing, validation, and read-only checks when a small tool reduces ambiguity.
- Do not ask for cloud account credentials.
- Do not recommend destructive actions without manual-only framing.
- Add compact golden cases for behavior changes.
- Keep evaluation deterministic; do not depend on LLM judgment for pass/fail gates.

## Evidence-First Discipline

A diagnosis is only as good as the evidence actually examined. Pattern
recognition proposes; evidence decides. Three rules bind every skill, regardless
of domain:

1. **Evidence overrides priors.** Memory recalls, reference notes, and
   error-string resemblance are hypotheses, not conclusions. When a primary
   artifact is available — the failing command, the script that built the
   request, the config in play, the full error body — read it before naming a
   root cause. A remembered "this looks like X" never substitutes for inspecting
   the artifact in front of you.
2. **Confidence is bounded by what you examined.** If a decisive artifact is
   available but not yet inspected, the diagnosis stays a *leading hypothesis*
   (confidence ≤ 0.5), however familiar the error looks. The hard caps live in
   `storageops-triage/references/confidence-rubric.md`.
3. **Falsify before concluding.** Fill the `What Would Falsify This` field and
   check the cheapest falsifier available. A diagnosis that no available evidence
   could disprove is not yet a diagnosis.

Errors that *resemble* a known signature are exactly where unverified priors
mislead — e.g. a digest/checksum error that looks like data corruption but is
actually a client-side encoding bug. Inspect the mechanism, not just the
surface symptom.

## Validation

Run:

```bash
python3 scripts/skill_integrity_check.py
python3 scripts/no_hardcoded_pricing.py
python3 scripts/reference_scope_check.py
python3 skills/storageops-eval-golden-cases/scripts/golden_case_validator.py \
  skills/storageops-eval-golden-cases/cases
python3 scripts/routing_contract_check.py
make validate
.venv/bin/python -m pytest
```

## Golden Cases

Each case has:

```text
cases/<case>/
├── description.md
├── input/
└── expected.json
```

`expected.json` must include:

- `expected_category`
- `expected_min_confidence`
- `must_include_evidence_keywords`
- `must_include_recommendation_keywords`
- `must_not_include`
- `required_report_sections`

Use canonical categories from `docs/skill-taxonomy.json`.

## Routing Contract

`docs/skill-taxonomy.json` is the routing contract. When adding a category,
skill, domain signature, golden case, or baseline output:

- map the category to one real `storageops-*` skill,
- keep aliases and signatures compact,
- set `baseline` only for categories with compact synthetic outputs,
- run `python3 scripts/routing_contract_check.py`.

## Size Budgets

The integrity check enforces:

| Item | Limit |
| --- | --- |
| `SKILL.md` | 40 KB |
| `docs/skill-taxonomy.json` | 20 KB |
| one golden-case input artifact | 10 KB |
| one golden case | 25 KB |
| all golden cases | 512 KB |

Large logs belong outside the repository. Commit reduced, synthetic, redacted samples.

`scripts/repo_size_gate.py` also rejects generated artifacts, Python caches,
oversized baseline outputs, oversized test fixtures, and runaway corpus growth.

## Eval Scripts

```bash
python3 skills/storageops-eval-golden-cases/scripts/eval_runner.py \
  --case skills/storageops-eval-golden-cases/cases/<case> \
  --output diagnosis.md

python3 skills/storageops-eval-golden-cases/scripts/eval_all.py \
  --cases skills/storageops-eval-golden-cases/cases \
  --outputs <your-saved-diagnoses-dir> \
  --json-out eval-current.json

python3 skills/storageops-eval-golden-cases/scripts/eval_all.py \
  --cases skills/storageops-eval-golden-cases/cases \
  --outputs skills/storageops-eval-golden-cases/baseline-outputs \
  --only-with-outputs

python3 skills/storageops-eval-golden-cases/scripts/regression_reporter.py \
  --baseline eval-baseline.json \
  --current eval-current.json
```

Baseline outputs should be compact and synthetic. Prefer structured `Category:`,
`Route:`, `Confidence:`, evidence, recommendations, and safety sections over
full narrative reports.

## Output Contract

Specialist skills should prefer this lightweight contract when the task is a
diagnosis. The fields are required concepts, not a rigid template:

- `Route`: canonical `storageops-*` skill or taxonomy category.
- `Confidence`: score or high/medium/low plus the reason.
- `Evidence Quality`: sufficient, partial, or insufficient.
- `Primary Diagnosis`: root cause type, affected layer, and assumptions.
- `Evidence`: observed facts only; keep inference separate.
- `Recommendations`: each with applicability conditions.
- `Validation Steps`: read-only checks or manual-only experiments that can prove
  or disprove the diagnosis.
- `What Would Falsify This`: evidence that would overturn the diagnosis.
- `Risks / Open Questions`: unresolved constraints, safety risks, and missing
  data.

Start by applying the full contract to high-risk skills such as security,
performance, and CLI/SDK diagnosis before expanding it to every skill.

## Maturity

Maturity increases `alpha` → `beta` → `mature`/`stable`. `core` is **orthogonal**:
it marks foundational skills (routing, reporting, safety), not a higher tier.

| Level | Meaning |
| --- | --- |
| `alpha` | Skill exists, but references, eval, and helper coverage are thin. |
| `beta` | References and integrity checks are in good shape. |
| `mature` | Adds useful deterministic helpers (parsers/analyzers). |
| `stable` | Adds representative golden cases and deterministic validation. |
| `core` | Foundational behavior (routing, reporting, safety) — orthogonal to the above. |
