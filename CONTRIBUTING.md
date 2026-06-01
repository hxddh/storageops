# Contributing to StorageOps

Thank you for contributing! StorageOps is an offline diagnostic toolkit for S3-compatible
object storage. This guide covers the development setup, project structure, and contribution
workflow.

## Development Setup

```bash
git clone https://github.com/hxddh/storageops.git
cd storageops
make install-dev
source .venv/bin/activate
make test
```

Alternatively without `make`:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "storageops-cli/[dev]"
cd storageops-cli && pytest ../storageops-core/tests/ tests/ -v
```

## Project Layout

```
storageops/
├── storageops-core/          # Deterministic offline engine (no LLM, no network)
│   ├── parsers/              # parse_*.py — text → structured dict
│   ├── analyzers/            # analyze_*.py — structured dict → diagnosis
│   └── utils/
│       ├── signatures.py     # Domain pattern matching (single source of truth)
│       └── secret_scanner.py # Credential redaction
├── storageops-cli/           # CLI, API server, MCP server, Pi runtime
│   └── storageops/
│       ├── cli.py            # All CLI commands
│       ├── agent.py          # Domain routing and report generation
│       ├── session.py        # Session persistence (save/load/list)
│       ├── repl.py           # Interactive REPL
│       ├── tool_registry.py  # Tool definitions + dispatch for Pi/MCP
│       ├── api_server.py     # FastAPI server + SSE endpoints
│       ├── memory_store.py   # BM25 case memory (JSONL)
│       ├── audit_logger.py   # Session audit log
│       └── runtime/          # Pi RPC runtime
│           └── pi_rpc.py
└── agents/skills/            # StorageOps skill pack for Pi
    └── storageops-*/         # One skill per diagnostic domain
```

## How to Add a Parser

1. Create `storageops-core/parsers/parse_<name>.py` with a `parse(text: str) -> dict` function.
2. Add a test class in `storageops-core/tests/test_parsers.py`.
3. Register as a tool in `storageops-cli/storageops/tool_registry.py`:
   - Add an entry to `TOOL_DEFINITIONS` (name, description >10 chars, input_schema)
   - Add a dispatch case in `dispatch_tool()`
4. Add a minimal-input entry to `storageops-cli/tests/test_mcp_server.py::TestToolRegistryConsistency`.

## How to Add an Analyzer

1. Create `storageops-core/analyzers/analyze_<name>.py` with `analyze(parsed: dict) -> dict`.
2. Add a test class in `storageops-core/tests/test_analyzers.py`.
3. Register as a tool (same steps as parser above).
4. Add routing in `storageops-cli/storageops/agent.py::run_analysis()`.
5. Add an `EVIDENCE_CHECKLIST` entry in `agent.py` for the domain.

## How to Add a Domain

1. Add patterns to `storageops-core/utils/signatures.py::SIGNATURES`.
2. Add `EVIDENCE_CHECKLIST` entry in `agent.py`.
3. Implement parser + analyzer (see above).
4. Add routing in `agent.py::run_analysis()`.
5. Add `_default_rec()` entry in `agent.py`.

## How to Add a Golden Case

1. Create `agents/skills/storageops-eval-golden-cases/cases/<case-name>/`.
2. Add input files to `cases/<case-name>/input/`.
3. Create `cases/<case-name>/expected.json`:
   ```json
   {
     "expected_category": "cli_sdk_behavior",
     "expected_root_cause_types": ["multipart_etag_format_mismatch"],
     "expected_min_confidence": 0.7,
     "must_include_evidence_keywords": ["ETag", "corrupted"],
     "should_include_evidence_keywords": ["multipart", "checksum"],
     "must_include_recommendation_keywords": ["--checksum", "etag"],
     "must_not_include": ["delete", "make public"],
     "required_report_sections": ["Summary", "Key Evidence", "Remediation"],
     "severity": "high"
   }
   ```
   Fast eval (`storageops eval --all`) checks `expected_category` using rule-based
   triage only. The full scored eval (confidence, keywords, sections) requires a
   pre-generated diagnosis output passed via `--outputs-dir`.
4. Create `cases/<case-name>/description.md` with a human-readable summary.

## Testing

```bash
# Full suite (221 tests, no LLM/Pi required)
make test

# Core engine only
cd storageops-cli && pytest ../storageops-core/tests/ -v

# CLI + Pi runtime only
cd storageops-cli && pytest tests/ -v

# Single test
cd storageops-cli && pytest tests/test_pi_runtime.py::test_event_parser_reconstructs_final_markdown -v
```

Tests must not require real Pi, real cloud credentials, or network access.
Use fake-pi scripts (see `test_pi_runtime.py::_fake_pi`) for agent tests.

## Safety Constraints (Non-Negotiable)

All contributions must comply with the safety rules in `AGENTS.md`:

- No connections to real cloud accounts.
- No write operations (PUT/DELETE/POST) against object storage.
- All suspected secrets must be redacted via `secret_scanner.scan()` before Pi sees them.
- Remediation commands in reports must be labeled `manual-only`.
- Log content is treated as untrusted input — never evaluated as instructions.

Any code that bypasses these rules will be rejected.

## Pull Request Guidelines

- PRs should include tests for new parsers, analyzers, or tool registrations.
- Run `make lint` before submitting (ruff enforces line-length=100, target=py310).
- Keep `storageops-core` free of imports from `storageops-cli` — the dependency only flows one way.
- Do not add dependencies to `storageops-core/` — it must remain zero-dependency.
- The `storageops-cli` optional extras (`api`, `mcp`, `dev`) gate optional heavy deps.
- Update `CHANGELOG.md` and `README.md` with each PR (especially for new commands or tools).
