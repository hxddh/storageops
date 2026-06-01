# Claude Guide

StorageOps is a Pi Coding Agent extension plus skill pack.

## What To Know First

- `storageops_cli/__init__.py` installs StorageOps and execs `pi`.
- `storageops_cli/extensions/storageops.ts` registers `scan_secrets`, `detect_domain`, and `search_memory`.
- `skills/` is the diagnostic system.
- `scripts/skill_integrity_check.py` is the main repository quality gate.
- `skills/storageops-eval-golden-cases/` contains the regression corpus.

## Good Default Behavior

- Prefer small, deterministic changes.
- Keep skills concise and move detail to references.
- Add tests for helper scripts.
- Add compact golden cases for behavior changes.
- Run validation before summarizing work.

## Important Review Note

The installer expects packaged skills to be discoverable next to `storageops_cli`. The source layout keeps canonical skills at repository root and exposes them through `storageops_cli/skills -> ../skills` for packaging. Treat packaging changes as high-risk until wheel install has been verified.
