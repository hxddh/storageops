# Agent Guide

This file is for coding agents working in the StorageOps repository.

## Mental Model

StorageOps is not a standalone agent runtime. It is:

- a Python installer/launcher,
- one Pi TypeScript extension,
- a root-level `skills/` tree,
- deterministic helper and eval scripts.

Pi Coding Agent provides the conversation loop, sessions, model calls, and tool dispatch.

## High-Risk Area

Packaging is the most fragile part of this repo. `storageops_cli.__init__._package_data_dir()` expects packaged data to expose both `extensions/` and `skills/`. The source tree keeps canonical skills at repository root and exposes them to packaging through `storageops_cli/skills -> ../skills`. Any distribution change must verify an installed wheel can run `storageops install`.

## Change Workflow

1. Read the relevant skill, script, or installer code first.
2. Keep changes scoped.
3. Do not commit large raw logs or credentials.
4. Run the quality gates.
5. Update docs and changelog for user-visible changes.

## Validation Commands

```bash
python3 scripts/skill_integrity_check.py
python3 skills/storageops-eval-golden-cases/scripts/golden_case_validator.py \
  skills/storageops-eval-golden-cases/cases
make validate
.venv/bin/python -m pytest
```

## Editing Skills

Every skill should keep:

- YAML frontmatter,
- decision tree,
- evidence requirements,
- workflow,
- output contract,
- references with `Read when:` guidance.

Use `docs/skill-quality-guide.md` and `docs/skill-taxonomy.md` as the source of truth for quality expectations.
