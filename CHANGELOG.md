# Changelog

## 2026-06-02 — v0.4.14: PyPI publishing, Pi auto-install, install verification

- **PyPI publishing**: added `.github/workflows/publish.yml` with PyPI Trusted Publisher
  (OIDC) so releases are published automatically on `v*` tags. A pre-publish job
  verifies that the tag version matches `pyproject.toml` to prevent version drift.
- **Pi auto-install**: `storageops install` now detects whether Pi Coding Agent is
  present and installs it via `npm install -g @earendil-works/pi-coding-agent`
  automatically when it is absent. If npm is not available the command exits with
  a clear error and a link to nodejs.org. When Pi is present but below the minimum
  version, the installer warns and prints the upgrade command rather than
  auto-upgrading, to avoid disrupting existing Pi configurations.
- **Install verification**: replaced the previous unconditional "installation complete"
  message with a structured post-install summary that reports the status of each
  component (StorageOps files, Pi Coding Agent, API key) and exits non-zero only
  when the tool cannot run at all (Pi missing). A missing API key is reported as a
  warning with configuration instructions, not a hard failure.
- **No-emoji CLI output**: removed all emoji from CLI print statements in
  `storageops_cli/__init__.py` for compatibility with terminals and log pipelines
  that do not handle Unicode correctly.
- **Docs**: updated README Quick Start with the explicit Pi install step, an
  Ubuntu/Debian pip note, and the corrected skill count (16). Updated
  `docs/getting-started.md` Prerequisites to list Node.js as a requirement and
  document the auto-install behavior.
- **Skill count**: corrected "15 diagnostic skills" to "16 diagnostic skills" in
  README (the eval skill pack was always present in code but the prose was inconsistent).

## 2026-06-02 — v0.4.13: Eval matcher hardening

- **Eval matcher**: added structured `Category`, `Route`, and `Confidence` field parsing before fallback text matching.
- **Keyword matching**: replaced naive substring checks with deterministic token/literal matching for short tokens, symbolic keywords, and CJK text.
- **Safety eval**: refined forbidden-output checks to ignore explicit safe-negation contexts such as "do not delete bucket" while still catching unsafe recommendations.
- **Tests/docs**: added matcher regression coverage and documented compact structured baseline-output expectations.

## 2026-06-02 — v0.4.12: Routing contract alignment

- **Routing contract**: extended `docs/skill-taxonomy.json` with signatures and baseline eligibility so categories, skills, aliases, and eval coverage share one contract.
- **Validation**: added `scripts/routing_contract_check.py` and CI coverage for taxonomy, registry, golden cases, baseline outputs, and deterministic domain signatures.
- **Baseline coverage**: added compact outputs for big-data small-file and event-notification prefix-filter cases, bringing baseline eval to 8 cases.
- **Docs**: updated taxonomy and quality guidance for maintaining routing contract alignment.

## 2026-06-02 — v0.4.11: Baseline eval and package quality gates

- **Eval baseline**: added compact baseline outputs for six high-value golden cases and an `eval_all.py --only-with-outputs` mode for subset scoring.
- **Size gates**: added `scripts/repo_size_gate.py` to reject generated artifacts, oversized fixtures, oversized golden cases, and baseline corpus growth.
- **Package check**: added `scripts/package_check.py` and CI coverage for wheel/sdist skill assets, extension presence, and Python cache exclusion.
- **CI/docs**: wired baseline eval, repo size gates, and package checks into CI and contributor documentation.

## 2026-06-02 — v0.4.10: Review bug fixes and real CI gates

- **CI**: GitHub Actions now installs dev dependencies, runs skill integrity checks, validates golden cases, and runs pytest.
- **Security tooling**: fixed public-policy detection for list/dict principal forms, broad resources, `NotAction`, and `NotPrincipal`; explicit Deny statements are now informational.
- **Credential loading**: fixed standard AWS credentials parsing for `key=value` profile files.
- **Routing/eval**: aligned deterministic domain detection with skill names, added protocol/big-data/CORS signatures, improved confidence scoring, and made eval enforce confidence thresholds.
- **Packaging/docs**: excluded Python cache files from source distributions and clarified skill counts, examples, changelog, and credential-loader security posture.

## 2026-06-02 — v0.4.9: Merge install settings preservation

- **Merge install fix**: `storageops install --merge` now preserves existing Pi `skills` paths and appends StorageOps' `../skills` path once instead of replacing the whole list.
- **Tests**: added CLI installer coverage for skill-path merging and settings preservation.
- **Version sync**: bumped the package and registry header to v0.4.9 for the installer bugfix release.

## 2026-06-02 — v0.4.8: Documentation rewrite and review notes

- **Documentation rewrite**: refreshed README, operator guides, contributor/security notes, architecture docs, CLI reference, quick reference, tutorial, skill quality guide, taxonomy/routing docs, dependency map, API matrix, and rclone examples.
- **Review visibility**: documented the packaging-data contract where root-level skills are exposed through `storageops_cli/skills -> ../skills` and must remain aligned with installer lookup paths.
- **Version sync**: bumped the package and registry header to v0.4.8 for the documentation-only release.

## 2026-06-02 — v0.4.7: Output contracts and size gates

- **Output contracts**: softened all skill output sections from rigid exact templates to required-field contracts.
- **Size gates**: added integrity-check budgets for SKILL.md files, taxonomy JSON, golden-case inputs, individual cases, and total golden-case corpus size.
- **Documentation**: updated skill quality and taxonomy docs with enforced repository size budgets.

## 2026-06-02 — v0.4.6: Endpoint reachability checker

- **Network tooling**: added `endpoint_reachability_test.py` for read-only DNS, TCP, TLS, and HTTP HEAD checks against an explicitly provided endpoint.
- **Layer classification**: reports the first failing layer as DNS, TCP, TLS, HTTP, application, or reachable.
- **Skill integration**: wired the checker into `storageops-network-endpoint-access` guidance and documented authorized-use constraints.
- **Tests**: added offline unit coverage for endpoint parsing, failure classification, and application-level HTTP status handling.

## 2026-06-02 — v0.4.5: SigV4 evidence parser

- **Protocol tooling**: added `parse_sigv4_error.py` to extract SigV4 error code, StringToSign, CanonicalRequest, credential scope, signed headers, and likely inspection points from XML/debug logs.
- **Skill integration**: wired the parser into `storageops-s3-protocol-compatibility` guidance and replaced the placeholder script note with concrete usage.
- **Tests**: added parser coverage for service XML responses and client debug blocks.

## 2026-06-02 — v0.4.4: Specialist diagnosis case coverage

- **Coverage**: added compact diagnosis golden cases for access-log delete storms, multipart ETag verification, big-data small-file queries, notification prefix filters, and migration metadata loss.
- **Regression suite**: expanded golden cases from 28 to 33 while keeping inputs small and synthetic.
- **Documentation**: updated eval examples and version references for the expanded suite.

## 2026-06-02 — v0.4.3: Batch golden-case evaluation

- **Batch eval**: added `eval_all.py` to evaluate saved outputs across many golden cases and emit regression-ready JSON summaries.
- **Eval summaries**: added PASS/SOFT_FAIL/HARD_FAIL/MISSING counts, pass rate, and per-category aggregation for saved-output suites.
- **Tests**: added coverage for batch eval summaries, missing outputs, and taxonomy-mapped skill scoring.
- **Documentation**: updated eval and skill quality docs with batch evaluation and regression baseline commands.

## 2026-06-02 — v0.4.2: Skill taxonomy and routing quality gates

- **Taxonomy contract**: added `docs/skill-taxonomy.json` and `docs/skill-taxonomy.md` to map golden-case categories to primary skills.
- **Routing coverage**: added 8 compact routing golden cases for ambiguous 403/signature, mount/performance, CORS, Spark committer, access-log, notification, migration, and stale-read scenarios.
- **Validation**: upgraded skill integrity and golden-case validators to reject unknown `expected_category` values.
- **Eval scoring**: `eval_runner.py` now accepts either the canonical category or the mapped skill name in diagnostic output.
- **Documentation**: updated skill quality and eval docs for taxonomy-backed golden cases and repository size budgets.

## 2026-06-01 — Skill quality gates and reference integrity

- **Reference integrity**: aligned SKILL.md bundled-resource links with real files and added missing domain references for big data, consistency, event notification, and migration skills.
- **Metadata consistency**: synchronized `skill-registry.yaml` maturity/mode values with SKILL.md frontmatter and moved the registry contract marker to v4.
- **Quality gates**: added `scripts/skill_integrity_check.py` and wired `make validate` to verify skill metadata, references, tools, registry paths, and golden-case schemas.
- **Eval automation**: implemented deterministic golden-case validator, unsafe-output scanner, single-case eval runner, and regression reporter.
- **Documentation**: added `docs/skill-quality-guide.md` to define skill structure, validation commands, golden-case requirements, and maturity rules.

## 2026-06-01 — Review fixes: merge skills path, memory search, skill registry sync

- **Merge install fix**: copy skills to the directory referenced by each target agent's `../skills` setting, so `storageops install --merge` uses `~/.pi/skills`.
- **Session memory fix**: `search_memory` now resolves sessions from `PI_CODING_AGENT_DIR` before falling back to `~/.pi/agent`.
- **Skill registry sync**: added `storageops-access-log-analysis` to registry and routing docs; updated skill-pack counts from 15 to 16.
- **Robustness**: pi version detection now extracts semver from prefixed version output; auth env injection accepts provider keys that do not start with `sk-`.

## 2026-06-01 — Smart install, PI_CODING_AGENT_DIR fix, api-key persistence

- **PI_CODING_AGENT_DIR fix**: Pi 0.78.0 uses `PI_CODING_AGENT_DIR` to resolve agent config, not `PI_HOME`. Directory restructured to `~/.storageops/agent/`.
- **API key persistence**: Added `~/.storageops/agent/api-key` plain-text file support. `_inject_auth_env()` reads it before launching Pi — completely shell-independent, works regardless of `.bashrc`/`.profile` sourcing.
- **Smart install detection**: `storageops install` detects existing Pi config (`~/.pi/`) and offers interactive choice: isolated (`~/.storageops/`) or merged (`~/.pi/`).
- **Pi version guard**: Warns if pi < 0.78.0 (Extension API requirement).
- **Extension moved**: `storageops_cli/extensions/storageops.ts` — removed from `.pi/extensions/` to avoid Pi auto-discovery conflicts.
- **Improved install guidance**: Three API key configuration methods shown at install completion.

## v0.4.0 — 2026-06-01: Lightweight Pi Extension Redesign

**Zero Python agent code** — the entire 48-file Python agent package has been deleted.
StorageOps is now a pure Pi Coding Agent extension + skill pack.

### Removed
- **storageops/** Python package (48 files) — all agent loop, session management,
  tool dispatch, CLI, REPL, API server, MCP server, config, audit, diagnostics
- **parsers/**, **analyzers/**, **utils/** directories — 21 files deleted.
  LLM reads raw logs directly; no pre-parsing needed.
- **tool_bridge.py** + `spawnSync` — tools now run inline in TypeScript extension
- **docs/review/** — 7 old review documents removed

### Added
- **`.pi/extensions/storageops.ts`** — rewritten as standalone TypeScript extension
  with 3 inline tools: `scan_secrets`, `detect_domain`, `search_memory`
- **`storageops_cli.py`** — thin CLI shim that forwards to `pi`

### Changed
- **skills/** moved to root (was `agents/skills/`)
- **All SKILL.md files** updated — `recommended_tools` reduced to 3 tools
- **README, AGENTS.md, docs/** — completely rewritten for new architecture
- **pyproject.toml** — slimmed to optional thin CLI, no heavy deps

### Architecture
- **Agent loop**: Pi Coding Agent (was custom agent.py)
- **Session**: Pi session manager (was custom session.py)
- **Tools**: Pi Extension API (was tool_bridge.py + if-elif dispatch)
- **Diagnostic logic**: SKILL.md instructions (was parsers/analyzers)
- **UI**: Pi TUI (was custom display.py + repl.py)

## v0.3.0 — 2026-06-01: Complete architecture rebuild

**Unified package** — merged `storageops-cli` + `storageops-core` into single `storageops` package.
No more sys.path hacks or dual-package coordination.

**Append-only session** — JSONL event log + meta.json sidecar.
Session is NEVER read-then-rewritten. Resume works correctly on every turn.

**Stateless agent** — `converse(session, input, display)`. No class, no modes, no global state.
Model decides when to use tools vs chat.

**Flat architecture** — `core/`, `ui/`, `cli/`, `runtime/` directories deleted.
All modules at package root. Import depth ≤ 2.

**Pi events as raw JSON** — zero translation layer. Pi upgrades require zero changes.

**Net**: ~4500 lines deleted, ~2000 new, -56% code, -60% directories.

---

## 2026-06-01 — Architecture refactor: natural conversational agent

**Core: prompt -> identity, no mode switching**
- Rewrote `pi_diagnosis_prompt.md` from 2500+-token diagnostic manual to ~500-token
  natural identity prompt. No mode switching — the model decides whether to chat,
  diagnose, or use tools based on context.
- Removed `pi_chat_prompt.md` — one prompt for all modes.
- Removed `_is_chat_message()` keyword detection and all chat/diagnose branching.

**Core: PiSession — persistent Pi process across turns**
- New `PiSession` class in `runtime/pi_rpc.py`: maintains one Pi subprocess across
  multiple turns. Conversation history is preserved — the model remembers previous
  interactions without needing to rebuild context.
- `PiRpcRuntime` kept for one-shot CLI commands (`triage`, `analyze`, `eval`).
- First turn: sends full system prompt + evidence file path.
  Subsequent turns: sends just the user message. Pi retains context.

**Core: non-blocking safety lint**
- `validate_agent_report()` → `safety_lint()`: scans for secrets and dangerous
  recommendations but NEVER blocks output. Safety notes appended as gentle reminders.
- YAML frontmatter validation removed from the agent pipeline (still available
  for eval/tests via `validate_report()`).

**REPL: simplified streaming display**
- `_StreamDisplay` simplified from 5-state dispatch (thinking/tool/YAML/report/chat)
  to 2 phases: thinking → response. No more YAML-collecting logic or mode-dependent
  formatting. All model output streams naturally.
- `_run_turn()` uses persistent `_pi_session` singleton; restarts on `/clear` or
  `/resume`.

## 2026-06-01 — Amp-style slash commands + command history + syntax highlighting

- **`/editor` command**: open `$EDITOR` (vim/nano) to write long prompts or paste large logs.
  Comment lines (`#`) are stripped; save-and-exit sends the prompt to Pi.
- **Shell mode (`$ cmd`)**: run shell commands inline; stdout (first 200 chars) is captured
  and added to session evidence for context-aware diagnosis.
- **Fuzzy `@file` matching**: glob patterns (`@*.log`, `@/tmp/my-log*`) and prefix matching
  (`@s5cmd` → most recent `s5cmd*` file by mtime). Absolute paths supported.
- **`/view` command**: opens the last assistant report in `less -R` pager for full-screen
  browsing; falls back to first 50 lines if less is unavailable. Applies pygments syntax
  highlighting when installed (YAML/JSON/bash/code blocks).
- **`/history` command**: shows last N interactive commands (`/history <N>`); defaults to 20.
  Readline history persists to `~/.storageops/history` with `↑`/`↓` and `Ctrl+R` search.
- **Progress timestamps**: elapsed seconds shown on each tool call result during streaming.
- **Streaming fix**: `_StreamDisplay` event handlers updated for actual Pi JSONL format
  (`tool_execution_start`/`tool_execution_end` replacing `tool_use`/`tool_result`;
  `text_start` supplementing `text_delta`).
- **`cli.py` fix**: removed stale `_LiveProgress` reference → `_StreamDisplay`.

## 2026-06-01 — Pi Extension + RPC protocol fix

- **Pi Extension** (`.pi/extensions/storageops.ts`): all 21 StorageOps diagnostic tools are
  now registered natively in Pi via `pi.registerTool()`. Pi's LLM can call them directly during
  multi-turn diagnosis sessions without any MCP or text-based tool list.
- **`runtime/tool_bridge.py`**: lightweight Python bridge subprocess. Reads `{tool, inputs}` from
  stdin, calls `dispatch_tool()`, writes JSON result to stdout. Called by the TypeScript Extension.
- **RPC protocol fix** (`runtime/pi_rpc.py`):
  - Request type corrected from `"diagnose"` (unsupported) to `"prompt"` (real Pi command)
  - Model configuration sent via `set_model` command before `prompt`
  - `stdin` kept open during the session (previously closed immediately, blocking all tool calls)
  - Terminal event updated from `final_report` to `agent_end` (real Pi protocol)
  - Report extracted from `agent_end.messages[].content[].text`
  - Streaming via `message_update.assistantMessageEvent.text_delta`
  - Fixed `ValueError: I/O operation on closed file` when draining stderr after `stdin.close()`
- **`pi_diagnosis_prompt.md`**: removed hand-written tool list (tools now registered natively);
  updated evidence collection strategy to call tools directly.
- **Tests**: fake Pi helper updated to emit real Pi RPC events (`agent_start`,
  `message_update/text_delta`, `agent_end/messages`). 109/109 tests pass.
- **Architecture docs** (`ARCHITECTURE.md`, `CLAUDE.md`, `README.md`, `docs/cli-reference.md`):
  updated to reflect Pi Extension as the correct tool registration path.

## 2026-05-31 — Pi Coding Agent-style REPL rewrite

- **`repl.py` complete rewrite**: interactive session now matches Pi Coding Agent / Ampcode UX
- **Single-Enter submit**: removed double-Enter (empty-line) submission model; press Enter once to send. Paste detection via `select` collects multi-line clipboard content as one message.
- **Minimal banner**: `StorageOps  anthropic  ·  type / for commands  ·  Ctrl+C to interrupt  ·  /exit to quit`
- **Session ID on startup**: `  Session  a3f2b1c8` shown immediately after banner (like Pi/Ampcode)
- **Removed UX noise**: domain classification (`Domain: security_iam_policy 91%`), evidence block counts, `has_log_content` gate, and `_first_turn` hint hack are all gone — the interface is a clean conversation
- **Tool call display**: verbose mode shows `⏺ tool_name · result_summary` per tool invocation
- **New `/status` command**: shows session ID, turn count, Pi status, API key status, verbose toggle
- **Code reduction**: 758 lines → 340 lines (−55%)
- **Docs**: README, cli-reference, getting-started, ARCHITECTURE, CHANGELOG updated to reflect new UX

## 2026-05-31 — httpmon integration + full documentation rewrite

- **httpmon integration**: `parse_httpmon_log` parser captures wire-level S3 signals from
  httpmon NDJSON (`--format json`) and HAR (`--har`) output. Auth header values are classified
  (sigv4/presigned/anonymous) but never exposed.
- **MCP tool**: `parse_httpmon_log` registered in `tool_registry.py`; available to Pi and
  Claude Desktop via MCP.
- **Skills v2 recommended tool calls**: `parse_httpmon_log` added to `storageops-performance-diagnosis`
  and `storageops-network-endpoint-access` recommended tool tables.
- **README**: httpmon installation, three usage patterns, and "what httpmon reveals" comparison table.
- **Docs overhaul**: `CHANGELOG.md`, `docs/cli-reference.md`, `docs/getting-started.md`,
  `CONTRIBUTING.md`, `ARCHITECTURE.md`, `storageops-cli/README.md`, `storageops-core/README.md`,
  and `docs/tutorial.md` all rewritten to reflect current CLI commands, install flow, and architecture.

## 2026-05-25 — Modern CLI commands + Skills v2 contract

- **Session persistence**: REPL sessions auto-saved to `~/.storageops/sessions/`; each session has
  a unique ID and timestamp. Evidence blocks and conversation turns are preserved across restarts.
- **`storageops resume`**: list recent sessions or resume a specific session by ID.
- **`storageops config list/get/set`**: manage `~/.storageops/config.json` from the CLI;
  API key stored under `api_key`, provider under `provider`.
- **`storageops update`**: re-downloads Pi binary and reinstalls skills without a full reinstall.
- **`storageops scan`**: renamed from `batch`; `batch` retained as a hidden alias.
- **Hidden aliases**: `agent` → `diagnose`; `batch` → `scan`; `analyse` → `analyze`.
- **Skills v2 contract**: all 15 skills upgraded with structured frontmatter (`maturity`, `mode`,
  `estimated_tokens`, `trigger_keywords`, `recommended_tools`), Output Envelope v2
  (`confidence_factors`, `evidence_quality_score`, `next_actions`), Recommended Tool Calls table,
  Light/Heavy dual mode, and Thinking framework blockquote.
- **`skill-registry.yaml` v2.0**: updated to reflect v2 contract, maturity levels, and all 15 skills.
- **`storageops-data-consistency`**: expanded from 64-line stub to a full skill with complete
  diagnosis workflow, root cause pattern library, and output requirements.
- **README**: fully rewritten for human beginners and AI agents; includes REPL demo, session
  resume, slash commands, httpmon table, MCP tool table, Output Envelope v2 example, skills table
  with maturity column.

## 2026-05-17 — Interactive REPL + Pi auto-install + API key config

- **REPL (`storageops`)**: natural-language interactive session with multi-turn evidence accumulation.
- **`@file` references**: `> analyze this log @/var/log/s3-error.log` inlines file content.
- **Slash commands**: `/help`, `/clear`, `/doctor`, `/setup`, `/verbose`, `/exit`.
- **`storageops setup`**: guided wizard that installs Pi, selects LLM provider, and stores API key.
- **Pi auto-install**: `storageops setup` downloads Pi binary automatically; `storageops doctor`
  checks environment health and reports Pi status.
- **One-shot pipe**: `aws s3 cp s3://bucket/key . 2>&1 | storageops`.
- **README**: hero demo, 2-command install, provider table.

## 2026-05-10 — pip install + setup/doctor

- **pip-installable**: `pip install storageops` (PyPI); no git clone required.
- **`storageops setup`** and **`storageops doctor`** added as primary user-facing commands.
- Config stored at `~/.storageops/config.json`.
- **`storageops triage`** and **`storageops analyze`** work offline without Pi or an API key.
- **`storageops diagnose`**: sends redacted evidence to Pi and returns a validated markdown report.

## 2026-04-28 — Offline engine, Makefile, network parser

- `parse_network_diagnostics.py` — parses `dig`/`curl -v`/`ping` output.
- `analyze_network.py` — DNS/TLS/TCP/VPC endpoint root cause from parsed diagnostics.
- Makefile targets: `make test`, `make lint`, `make eval`.
- SKILL.md files translated to English; v1 skill structure.
- All tests run without LLM, Pi, or network access.

## v0.1.0 — Skill Pack

- **10 diagnostic skills**: triage, S3 protocol, CLI/SDK, performance, mount, network, security,
  lifecycle, reporting, eval.
- **47 reference documents** covering SigV4, ETag, multipart, rclone, s5cmd, IAM policy, KMS,
  lifecycle, and more.
- **4 report templates**: customer, engineering note, reproduction checklist, diagnosis report.
- **5 golden cases** with `expected.json` validation schemas.
- **AGENTS.md + README.md** — project-level agent instructions.
- **`skill-registry.yaml`** — skill discovery and routing.
