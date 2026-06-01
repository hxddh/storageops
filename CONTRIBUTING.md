# Contributing

StorageOps is mostly a skill pack plus a thin installer. Good contributions keep behavior evidence-based, safe by default, and easy to regression test.

## Setup

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
storageops install --force
```

## Common Changes

### Add or Edit a Skill

1. Edit `skills/storageops-<domain>/SKILL.md`.
2. Keep the frontmatter aligned with `skill-registry.yaml`.
3. Put long provider details in `references/`.
4. Add or update compact golden cases when behavior changes.
5. Run validation before opening a PR.

### Add a Deterministic Helper

Place domain-specific helpers under the relevant skill:

```text
skills/storageops-<domain>/scripts/<tool>.py
```

Scripts should be offline or explicitly read-only, emit structured output where practical, and include tests under `tests/`.

### Add a Golden Case

Create:

```text
skills/storageops-eval-golden-cases/cases/<case>/
├── description.md
├── input/
└── expected.json
```

Keep inputs synthetic, redacted, and small. The integrity check enforces size budgets.

### Change the Extension

Edit `storageops_cli/extensions/storageops.ts`. It currently registers `scan_secrets`, `detect_domain`, and `search_memory` via Pi's extension API.

### Change Install or Launch Behavior

Edit `storageops_cli/__init__.py`. Be careful with:

- independent vs merge mode paths,
- `PI_CODING_AGENT_DIR`,
- package data lookup for skills and extensions,
- preserving existing Pi settings.

## Validation

Run:

```bash
python3 scripts/skill_integrity_check.py
python3 skills/storageops-eval-golden-cases/scripts/golden_case_validator.py \
  skills/storageops-eval-golden-cases/cases
make validate
.venv/bin/python -m pytest
```

## Pull Request Checklist

- The change is scoped and documented.
- No real credentials, customer logs, or large raw artifacts are committed.
- New helper scripts have tests.
- New golden cases use canonical categories from `docs/skill-taxonomy.json`.
- Version and changelog are updated for user-visible behavior.

## Release Notes

Use patch versions for quality gates, docs, helper scripts, golden cases, and installer fixes. Reserve larger version changes for major architecture or packaging changes.
