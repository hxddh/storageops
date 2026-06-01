# Contributing to StorageOps

StorageOps is a diagnostic agent for S3-compatible object storage, powered by Pi Coding Agent.

## Development Setup

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
pip install -e ".[dev]"
```

Or with make:
```bash
make install-dev
source .venv/bin/activate
```

## Project Layout

```
storageops/
├── session.py           ← append-only JSONL event log
├── agent.py             ← stateless conversation loop
├── pi_runtime.py        ← Pi subprocess manager
├── context.py           ← prompt construction
├── display.py           ← ANSI streaming renderer
├── repl.py              ← interactive REPL
├── picker.py            ← session selector UI
├── cli.py               ← all CLI commands
├── config.py            ← configuration management
├── tool_registry.py     ← 21 tool definitions + dispatch
├── action_tools.py      ← Pi extension tool wrappers
├── tool_bridge.py       ← stdin/stdout bridge for Pi extension
├── diagnostics.py       ← domain classification + analysis pipeline
├── pi_installer.py      ← Pi auto-installer
├── audit_logger.py      ← audit trail logger
├── audit_reader.py      ← audit trail reader
├── api_server.py        ← FastAPI REST server
├── mcp_server.py        ← MCP stdio server
├── parsers/             ← 12 log parsers (zero-dependency)
├── analyzers/           ← 10 diagnostic analyzers
├── utils/               ← secret_scanner, signatures
├── tests_core/          ← unit + smoke tests
└── prompts/
    └── identity.md      ← single identity prompt (~200 tokens)
```

## Testing

```bash
make test          # Run all tests
ruff check .       # Lint
```

## Architecture Principles

1. **Append-only session** — JSONL event log is never read-then-rewritten
2. **Pi events as raw JSON** — zero translation, zero custom types
3. **Stateless agent** — `converse()` is a pure function
4. **No mode switching** — the model decides chat vs diagnose
5. **Flat package** — no `core/`, `ui/`, `cli/`, `runtime/` nesting

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

## Adding a New Tool

1. Add a parser or analyzer module in `storageops/parsers/` or `storageops/analyzers/`
2. Register it in `tool_registry.py` (tool definition + dispatch handler)
3. Add the Pi extension definition in `.pi/extensions/storageops.ts`

## License

MIT
