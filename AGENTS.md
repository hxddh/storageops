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
make ci-local        # mirror CI validate job (offline; run before PR)
make validate-full   # alias for ci-local
make dev             # one-shot dev setup (venv, Node, storageops install)
```

`make validate` does not exercise the TypeScript extension — the routing,
provider, and trace logic is only covered by the extension behavioral tests, so
run `make ci-local` (or `make extension-tests`) when touching
`storageops_cli/extensions/storageops.ts`. `make package-check`, `install-smoke`,
and `diagnosis-smoke` need a wheel build or network/model key — see `docs/release.md`.

## Editing Skills

Every skill should keep:

- YAML frontmatter,
- decision tree,
- evidence requirements,
- workflow,
- output contract,
- references with `Read when:` guidance.

Use `docs/skill-quality-guide.md` and `docs/skill-taxonomy.md` as the source of truth for quality expectations.

## Cursor Cloud specific instructions

This is a CLI/skill-pack product — there is no long-running server or GUI. "Running
the app" means the `storageops` CLI plus the offline quality gates. Standard
commands live in the `## Validation Commands` section above, `Makefile`, and
`README.md`; the notes below are only the non-obvious cloud gotchas.

- **Console scripts are in `~/.local/bin`.** The update script installs with
  `pip install -e '.[dev]'`, which puts `storageops` and `pytest` in
  `~/.local/bin`. That dir is added to `PATH` via `~/.bashrc`; if a command says
  `storageops: not found`, run `export PATH="$HOME/.local/bin:$PATH"`.
- **Two Node versions exist; the default is too old for Pi.** `node` resolves to
  `/exec-daemon/node` (v22.14.0), which is **below** Pi's required 22.19+. To run
  `storageops install` or launch Pi, put the nvm Node first:
  `export PATH="$HOME/.nvm/versions/node/v22.22.2/bin:$PATH"` (or `nvm use 22`).
  The extension tests (`make extension-tests`) use `node --experimental-strip-types`
  and work on either Node, so plain `make validate-full` is fine without switching.
- **Pi, httpmon, and skills are already deployed** to `~/.storageops/` (via
  `storageops install`, persisted in the snapshot). `storageops doctor` should
  report everything `ok` except the API key. If `~/.storageops` is ever missing,
  re-run `storageops install` with the nvm Node on `PATH` (needs network for the
  npm Pi install).
- **Offline vs. live.** All gates and `make ci-local` / `storageops eval --baselines`
  run fully offline and need no key. A **live diagnosis**
  (`storageops --print '...'`) and `storageops smoke` require a model provider key
  (`ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`, etc.), which is not
  configured in this environment.
- **PR gate.** Run `make ci-local` before opening a PR; it mirrors the CI `validate`
  job. Use `make dev` for first-time setup (`scripts/dev_setup.sh`).
