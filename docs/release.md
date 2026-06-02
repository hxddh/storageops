# Release

StorageOps publishes to PyPI automatically from GitHub Actions.

## One-Time PyPI Setup

Configure PyPI Trusted Publisher for the `storageops` project before the first
release:

| Field | Value |
| --- | --- |
| PyPI project | `storageops` |
| Owner | `hxddh` |
| Repository | `storageops` |
| Workflow | `.github/workflows/publish.yml` |
| Environment | `pypi` |

No PyPI API token is stored in GitHub. Publishing uses GitHub OIDC through PyPI
Trusted Publisher.

## Release Flow

1. Update `pyproject.toml`, `skill-registry.yaml`, and docs/changelog version
   references.
2. Run the local quality gates:

   ```bash
   .venv/bin/python -m pytest
   make validate
   .venv/bin/python scripts/package_check.py
   python3 scripts/repo_size_gate.py
   python3 scripts/routing_contract_check.py
   python3 skills/storageops-eval-golden-cases/scripts/eval_all.py \
     --cases skills/storageops-eval-golden-cases/cases \
     --outputs skills/storageops-eval-golden-cases/baseline-outputs \
     --only-with-outputs
   ```

3. Merge the release PR to `main`.
4. Create and push a matching `v*` tag:

   ```bash
   git checkout main
   git pull --ff-only origin main
   git tag v0.4.16
   git push origin v0.4.16
   ```

The tag version must match `pyproject.toml`. For example, tag `v0.4.16` requires
`version = "0.4.16"`.

## What The Workflow Checks

`.github/workflows/publish.yml` runs on every `v*` tag and:

- verifies the tag version matches `pyproject.toml`,
- builds wheel and source distributions,
- runs `twine check` on `dist/*`,
- runs `scripts/package_check.py` to verify packaged skills and extension assets,
- publishes the same checked artifacts to PyPI through Trusted Publisher.

Use the workflow's manual `workflow_dispatch` preflight before the first real
release, or whenever release plumbing changes. Manual runs build and validate
the package but never publish to PyPI.
