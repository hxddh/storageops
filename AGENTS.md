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
make validate        # fast skill/extension/doc gates (greps the extension only)
make validate-full   # + pytest, extension behavioral tests, size/routing gates
```

`make validate` does not exercise the TypeScript extension — the routing,
provider, and trace logic is only covered by the extension behavioral tests, so
run `make validate-full` (or `make extension-tests`) when touching
`storageops_cli/extensions/storageops.ts`. `package_check.py`, `install-smoke`,
and `diagnosis-smoke` run in CI (wheel build / network) — see `docs/release.md`.

## Editing Skills

Every skill should keep:

- YAML frontmatter,
- decision tree,
- evidence requirements,
- workflow,
- output contract,
- references with `Read when:` guidance.

Use `docs/skill-quality-guide.md` and `docs/skill-taxonomy.md` as the source of truth for quality expectations.
