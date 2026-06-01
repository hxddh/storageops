# Architecture

StorageOps v0.4.7 is a **Pi Coding Agent extension + skill pack**.

## Design Principles

1. **Zero Python agent code** — no agent loops, session managers, or tool dispatchers in Python
2. **Skills over code** — diagnostic logic lives in SKILL.md instructions
3. **LLM-native extraction** — the model reads raw logs directly without pre-parsing
4. **Pi-native tools** — tools are registered via Pi's Extension API, no subprocess bridging

## Layers

```
┌─────────────────────────────────────────────┐
│               User / CLI / API              │
├─────────────────────────────────────────────┤
│           Pi Coding Agent (runtime)          │
│  ┌───────────────────────────────────────┐  │
│  │  Agent loop  │ Session JSONL │ Tools  │  │
│  │  Compaction  │ Stream events  │  TUI   │  │
│  └───────────────────────────────────────┘  │
│          │               │                   │
│  ┌───────▼───────┐  ┌────▼──────────────┐   │
│  │ storageops.ts  │  │ skills/*.SKILL.md  │   │
│  │ (3 tools)      │  │ (16 skill packs)   │   │
│  └───────────────┘  └────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Installation Layout

### Independent Mode

```
~/.storageops/
├── agent/                        ← PI_CODING_AGENT_DIR
│   ├── settings.json             ← Pi config (skills path, provider, model)
│   ├── api-key                   ← Optional: persistent API key (plain text)
│   ├── auth.json                  ← Optional: Pi-native provider credentials
│   ├── extensions/
│   │   └── storageops.ts         ← TypeScript extension (3 tools)
│   └── sessions/                 ← Pi-managed session logs
└── skills/                        ← 16 diagnostic skill packs
    ├── storageops-triage/
    ├── storageops-security-iam-policy/
    └── ...
```

### Merge Mode

```
~/.pi/
├── agent/                        ← Existing Pi config
│   ├── settings.json             ← Merged: user's + StorageOps keys
│   │   (original backed up as settings.json.storageops-backup)
│   ├── extensions/
│   │   └── storageops.ts
│   └── sessions/
└── skills/                        ← 16 diagnostic skill packs
```

## Extension (`storageops_cli/extensions/storageops.ts`)

The extension registers 3 tools with Pi's tool system:

| Tool | Implementation | Purpose |
|------|---------------|---------|
| `scan_secrets` | Inline TypeScript regex | Credential detection and redaction |
| `detect_domain` | Inline TypeScript regex | Domain classification from evidence |
| `search_memory` | fs read of Pi session JSONL | Past session search |

All tools run inline in Pi's TypeScript runtime. No Python subprocess, no tool_bridge, no sys.path hacks.

## Skills (`skills/`)

16 skill packs covering 12+ diagnostic domains. Each skill is a directory with:

```
skills/storageops-<domain>/
  SKILL.md              ← Instructions for the agent
  references/           ← Domain reference materials
  scripts/              ← Optional utility scripts
```

### Skill Activation

Skills are activated by trigger keywords in the conversation. The `detect_domain` tool provides automated domain classification.

### Skill Structure

Each SKILL.md has:

- **YAML frontmatter**: name, description, maturity, mode, trigger_keywords, recommended_tools
- **Light diagnosis**: Quick triage based on error patterns
- **Deep diagnosis**: Full root cause analysis with evidence chains
- **Report template**: Structured output format

### Skill Taxonomy

`docs/skill-taxonomy.json` maps stable golden-case categories to primary skills.
The taxonomy keeps routing tests, eval output, and documentation aligned without
duplicating large log fixtures in the repository.

## Session Model

Sessions are managed entirely by Pi Coding Agent:
- Append-only JSONL files stored at `{agent_dir}/sessions/`
- Automatic compaction when context window is full
- Multi-session support with resume

## Tool Execution

```
User says: "My s5cmd log shows 429 errors"

1. scan_secrets(user_log)         ← Run inline in extension
   → result: {findings: 0, redacted_text: "..."}

2. detect_domain(redacted_text)   ← Run inline in extension
   → result: {domains: [{domain: "performance-throttling", confidence: 0.9}]}

3. Pi loads storageops-performance-diagnosis SKILL.md
   ← Trigger keyword "429" matches

4. Agent follows skill instructions:
   - Analyze the log pattern
   - Identify s5cmd concurrency settings
   - Recommend: reduce --concurrency, add retry logic
```

## Comparison: v0.3.0 vs v0.4.0

| Aspect | v0.3.0 | v0.4.0 |
|--------|--------|--------|
| Python files | 48 | 1 (thin CLI shim) |
| Agent loop | Custom agent.py | Pi native |
| Session | Custom session.py | Pi native |
| Tools | tool_bridge.py + subprocess per call | Extension API inline |
| Parsers | 12 Python files | LLM-native (deleted) |
| Analyzers | 9 Python files | Skills instructions (deleted) |
| Tool dispatch | if-elif chain | Pi's tool registry |
| Display | Custom display.py | Pi TUI |
| REPL | Custom repl.py | Pi REPL |
| CLI | argparse subcommands | Pi + thin shim |
| Config | config.py | Pi settings.json |
| API | FastAPI api_server.py | Pi SDK |
| New domain | Write Python + edit 3 files | New SKILL.md |
| Directory count | 73 | ~25 |
