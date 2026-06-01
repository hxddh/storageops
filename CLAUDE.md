# CLAUDE.md — StorageOps AI Agent Guide

StorageOps is a **Pi Coding Agent extension + skill pack**.

## Project Structure

```
├── storageops_cli/__init__.py          # Install / launch CLI (240 lines)
├── storageops_cli/extensions/storageops.ts  # 3 inline TypeScript tools
├── storageops_cli/skills → ../skills   # Symlink for editable install
├── skills/                             # 16 diagnostic skill packs
│   ├── storageops-triage/SKILL.md
│   └── ...
├── docs/
└── pyproject.toml
```

## How It Works

```
User: storageops "question"
  → storageops_cli/__init__.py:main()
    → sets PI_CODING_AGENT_DIR to ~/.storageops/agent
    → exec's pi with all args forwarded

Pi (runtime):
  → loads storageops.ts extension (3 tools inline, TypeScript)
  → loads skills/*.SKILL.md (16 diagnostic instruction sets)
  → handles agent loop, sessions, tool dispatch natively
```

## Key Design Decisions

1. **Zero Python agent code** — Pi handles agent loop / session / tool dispatch
2. **Tools in TypeScript** — `storageops.ts` has `scan_secrets`, `detect_domain`, `search_memory` — inline, no subprocess
3. **Skills are markdown** — Each `SKILL.md` has YAML frontmatter + phased diagnostic instructions
4. **Two install modes** — Isolated (`~/.storageops/`) or merged (`~/.pi/`)
5. **Pi version guard** — Requires ≥ 0.78.0 (Extension API)

## Making Changes

- **Add tool**: Edit `storageops_cli/extensions/storageops.ts` → `pi.registerTool()`
- **Add skill**: Create `skills/storageops-<name>/SKILL.md` → update `skill-registry.yaml`
- **Modify install flow**: Edit `storageops_cli/__init__.py` → `cmd_install()`
- **Update docs**: Edit files in `docs/`, `README.md`, `AGENTS.md`

## Testing

```bash
pip install -e .
storageops install --force
storageops --print --no-session --api-key sk-xxx 'test query'
```
