# Release

StorageOps publishes to PyPI automatically from GitHub Actions when a release PR
is merged to `main`.

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
   make ci-local
   make package-check   # optional; wheel build + package_check.py
   ```

3. Merge the release PR to `main`.

The `Publish to PyPI` workflow runs on the resulting `main` push. If the
`pyproject.toml` version does not already exist on PyPI, the workflow publishes
it automatically. If the version already exists, the workflow skips publishing
instead of failing on a duplicate upload.

Optional compatibility path: create and push a matching `v*` tag to run the same
release workflow for a specific commit:

   ```bash
   git checkout main
   git pull --ff-only origin main
   git tag v0.4.57
   git push origin v0.4.57
   ```

When using the tag path, the tag version must match `pyproject.toml`. For
example, tag `v0.4.57` requires `version = "0.4.57"`.

## What The Workflow Checks

`.github/workflows/publish.yml` runs on every `main` push and `v*` tag. It:

- checks whether the current version already exists on PyPI,
- verifies the tag version matches `pyproject.toml`,
- runs `scripts/skill_integrity_check.py` and the full `pytest` suite, so a
  failing test or broken skill cannot be published,
- prepares verified gzip-compressed `httpmon` helper assets for packaging,
- builds wheel and source distributions,
- runs `twine check` on `dist/*`,
- runs `scripts/package_check.py` to verify packaged skills, extension assets,
  and bundled `httpmon` helpers,
- publishes the same checked artifacts to PyPI through Trusted Publisher when
  the version is not already present.

The generated helper assets live under `storageops_cli/_vendor/httpmon/*.gz`
during packaging and are ignored by Git. v0.4.57 packages the Linux amd64 helper
used by common cloud VMs; other platforms use the bounded download fallback.
Generated assets are included in the release artifacts but not committed to the
source repository.

Use the workflow's manual `workflow_dispatch` preflight before the first real
release, or whenever release plumbing changes. Manual runs build and validate
the package but never publish to PyPI.
