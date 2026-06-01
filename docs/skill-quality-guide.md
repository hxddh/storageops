# Skill Quality Guide

This guide defines the quality bar for StorageOps diagnostic skills. It turns the skill pack from a collection of prompts into a maintainable, testable diagnostic system.

## Quality Principles

1. **Progressive disclosure** — keep `SKILL.md` focused on workflow, evidence, tool use, and output; put detailed provider behavior in `references/`.
2. **No broken links** — every backticked `references/...` or `scripts/...` path in a `SKILL.md` must exist in that skill directory.
3. **Single metadata truth** — `skill-registry.yaml` must match each `SKILL.md` for `name`, `maturity`, `mode`, and path.
4. **Stable taxonomy** — every golden-case `expected_category` must map to a primary skill in `docs/skill-taxonomy.json`.
5. **Deterministic validation** — golden cases, unsafe-output scans, and integrity checks must run without LLM judgment.
6. **Safety first** — destructive, public-access, TLS-disabling, or credential-exposing recommendations must be blocked unless explicitly framed as unsafe analysis rather than a fix.

## Required Skill Shape

Every `skills/storageops-*/SKILL.md` should include:

- YAML frontmatter with `name`, `description`, `maturity`, `mode`, `trigger_keywords`, and `recommended_tools`.
- A decision tree or routing checklist.
- Evidence requirements and user clarification prompts.
- A step-by-step workflow.
- Tool/script usage instructions when deterministic helpers exist.
- A structured output template with evidence, root cause, confidence, recommendations, and limitations.
- A `References` section with `Read when:` guidance for each file.

## Validation Commands

Run these before merging skill changes:

```bash
python3 scripts/skill_integrity_check.py
python3 skills/storageops-eval-golden-cases/scripts/golden_case_validator.py \
  skills/storageops-eval-golden-cases/cases
make validate
```

## Golden Case Expectations

Each case under `skills/storageops-eval-golden-cases/cases/<case>/` must contain:

- `input/` with at least one artifact.
- `expected.json` with required category, confidence, evidence keywords, recommendation keywords, forbidden output patterns, and required report sections.
- `expected_category` matching a canonical category in `docs/skill-taxonomy.json`.
- `must_not_include` must be non-empty and include safety-relevant forbidden patterns.

Routing cases should set `"case_type": "routing"`, keep input artifacts short, and validate that triage names either the canonical category or the mapped skill.

## Repository Size Budget

- Keep `SKILL.md` files focused on workflow and evidence requirements; move details into references.
- Keep golden-case inputs synthetic, redacted, and small; avoid committing full debug logs.
- Keep deterministic helper scripts narrow and parse-oriented.
- Store large regression corpora outside the main repository and commit only manifests or reduced samples.

Use deterministic scripts:

```bash
python3 skills/storageops-eval-golden-cases/scripts/eval_runner.py \
  --case skills/storageops-eval-golden-cases/cases/<case> \
  --output diagnosis.md

python3 skills/storageops-eval-golden-cases/scripts/eval_all.py \
  --cases skills/storageops-eval-golden-cases/cases \
  --outputs diagnoses \
  --json-out eval-current.json

python3 skills/storageops-eval-golden-cases/scripts/unsafe_output_scanner.py \
  diagnosis.md --case skills/storageops-eval-golden-cases/cases/<case>
```

## Maturity Model

- **alpha** — SKILL.md exists, but references/evals are incomplete.
- **beta** — references are complete and integrity checks pass.
- **mature** — references are complete, helper scripts exist where useful, and domain-specific validation passes.
- **stable** — golden cases exist and deterministic validation passes.
- **core** — skill is a routing, reporting, or safety-critical foundation used across domains.

Do not mark a skill as `stable` unless its bundled-resource links are valid and at least the relevant integrity checks pass.
