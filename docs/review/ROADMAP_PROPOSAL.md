# Roadmap Proposal

**Author:** StorageOps Code Review, 2026-05-30  
**Status:** Proposal — pending owner review  
**Basis:** Findings from full codebase review. See `REVIEW_SUMMARY.md` for evidence.

---

## Guiding Principles

1. **Correctness before features** — fix verified bugs before adding new capabilities
2. **Test infrastructure is not optional** — pytest must work before claiming any version is stable
3. **Honest capability claims** — README and AGENTS.md must accurately reflect what is implemented
4. **Security by default** — redaction, offline-only, no cloud ops — these are non-negotiable invariants
5. **Evidence-based conclusions** — no finding without cited evidence; no recommendation without minimum evidence threshold

---

## v0.1 Skill Pack Hardening + Core Bug Fixes

**Target:** 4 weeks from review date  
**Prerequisites:** None  

### Goals

**P0 — Must complete for v0.1 to be declared stable:**
- [ ] Fix `smoke_test.py` to be pytest-compatible (SO-001)
- [ ] Fix `detect_throttling.py` double-counting bug (SO-002)
- [ ] Fix `storageops eval --all` filename mismatch (SO-003)
- [ ] Add `ruff check .` and `pytest -q` to CI (SO-010, requires SO-001 + SO-011 first)

**P1 — Should complete for v0.1:**
- [ ] Fix hierarchical prefix overlap in `parse_lifecycle_xml.py` (SO-004)
- [ ] Fix `avg_object_age_days=0` false positive in `analyze_cost.py` (SO-005)
- [ ] Add `s3:Get*` wildcard to `analyze_policy.py` (SO-006)
- [ ] Add stderr warning to `--no-redact` flag (SO-009)
- [ ] Add Alibaba Cloud + Tencent Cloud patterns to `secret_scanner.py` (SO-008)
- [ ] Write `SECURITY.md` and `CONTRIBUTING.md` (SO-014)

**P2 — Nice-to-have for v0.1:**
- [ ] Fix all 24 ruff violations (SO-011)
- [ ] Remove dead variables from `agent.py` (SO-012)
- [ ] Fix `scan_unsafe()` false positive for `manual-only:` prefix (SO-015)
- [ ] Add `do_not_use` sections to 3 skills missing them

### Deliverables

- `pytest -q` passes on Python 3.9–3.13
- `ruff check .` exits 0
- `storageops eval --all docs/examples/` finds and scores at least 1 case
- No verified logic bugs in shipped analyzers
- `SECURITY.md` and `CONTRIBUTING.md` exist

### Not in Scope

- New parsers or analyzers
- LLM integration
- Network endpoint analyzer implementation

---

## v0.2 Core Stabilization + Packaging

**Target:** 6 weeks after v0.1  
**Prerequisites:** v0.1 complete  

### Goals

**Packaging:**
- [ ] Convert `storageops-core` to proper installable package with `__init__.py` and `pyproject.toml` (SO-007)
- [ ] Remove all `sys.path` manipulation from CLI and tests
- [ ] Update `storageops-cli/pyproject.toml` to declare `storageops-core` as dependency
- [ ] Align version number: `pyproject.toml` `1.0.0` → `0.2.0`

**Analyzer completeness:**
- [ ] Implement `analyze_network_endpoint.py` (SO-013)
- [ ] Create `parse_network_log.py` for curl/dig/traceroute output
- [ ] Wire `parse_s5cmd_log.py` into agent's `run_analysis()` for cli_sdk and protocol domains

**Test coverage:**
- [ ] Unit tests for every module in `storageops-core` (currently zero unit tests)
- [ ] Parametrized test cases for known edge cases per analyzer
- [ ] Add golden cases for 4 currently-uncovered domains: `cli_sdk_diagnosis`, `performance_throughput`, `network_endpoint_access`, `triage`

**Skill Pack:**
- [ ] Add `safety_rules` to all skills missing it
- [ ] Add `do_not_use` to all skills missing it
- [ ] Add `references/` to `storageops-triage`
- [ ] Add benchmark baselines to `storageops-performance-diagnosis`

### Deliverables

- `pip install storageops-core` works in isolation
- All 9 diagnostic domains return real analysis (no stubs)
- ≥ 15 golden cases (up from 5)
- 100% module coverage in smoke tests

---

## v0.3 CLI Reliability

**Target:** 6 weeks after v0.2  
**Prerequisites:** v0.2 complete  

### Goals

**CLI stability:**
- [ ] Fix `cmd_report()` 3000-char hard truncation → make configurable via `--max-length` flag
- [ ] Add `--output FILE` flag to `storageops report`
- [ ] Fix triage confidence formula (matched/total_matched, not matched/total_patterns)
- [ ] Add batch mode: `storageops analyze --batch <directory>` processes multiple input files
- [ ] Add input size limit with clear error message (e.g., max 50MB)

**Eval:**
- [ ] Add `storageops eval generate` subcommand to produce output file from agent run (enables batch eval)
- [ ] CI gate: `storageops eval --all docs/examples/` passes with score ≥ 0.7

**Documentation:**
- [ ] Write `ARCHITECTURE.md` with layer diagram
- [ ] Write `ROADMAP.md` (official, replaces this proposal)
- [ ] Add `docs/examples/*.md` for each domain (9 total)
- [ ] Ensure all README examples are runnable end-to-end

**Report quality:**
- [ ] All templates from `storageops-evidence-reporting` usable via `storageops report --template <name>`
- [ ] Exit codes: 0=success, 1=error, 2=findings-requiring-action, 3=insufficient-evidence

### Deliverables

- All CLI examples in README run successfully on fresh install
- `storageops report --template customer-report` works
- Exit code semantics documented and implemented
- `storageops eval --all` CI gate green

---

## v0.4 Agent Prototype (Offline)

**Target:** 8 weeks after v0.3  
**Prerequisites:** v0.3 complete  

### Goals

**Honest agent architecture:**
- [ ] Rename or document `storageops agent` as "offline diagnostic orchestrator" until LLM is added
- [ ] Load skill routing from `skill-registry.yaml` (remove hardcoded DOMAIN_SKILL_MAP)
- [ ] Centralize evidence checklists in `skill-registry.yaml` (eliminate duplication with SKILL.md)
- [ ] Implement real evidence quality classification based on checklist matching (replace dead `found_count`)

**Context / state management:**
- [ ] Implement case context that persists across `storageops agent` turns (save/load from JSON file)
- [ ] Session ID for grouping multiple analysis steps into one diagnostic case
- [ ] Audit log: every action, input hash, output hash, timestamp stored in `~/.storageops/audit.jsonl`

**LLM integration prototype (BYOK):**
- [ ] Add `--llm-provider` flag (anthropic, openai, ollama) — all optional, offline-only by default
- [ ] When LLM provider configured: pass structured evidence summary (NOT raw log) to LLM for natural-language diagnosis
- [ ] Prompt injection protection: wrap all user-provided content in XML delimiters with explicit untrusted-content framing
- [ ] LLM output always passed through `scan_unsafe()` before returning to user
- [ ] Add prompt injection protection notes to all SKILL.md files

**Skill Pack:**
- [ ] `storageops-triage` SKILL.md updated with LLM routing instructions
- [ ] All skills have explicit prompt injection mitigation notes

### Deliverables

- `storageops agent --llm-provider anthropic` (with API key) provides LLM-enhanced diagnosis
- Offline mode (`storageops agent` without LLM) still works fully
- Audit log written for all agent sessions
- Case context persists across invocations within a session
- All unsafe outputs filtered through `scan_unsafe()` gate

---

## v1.0 Production-Ready Diagnostic Agent

**Target:** 12 weeks after v0.4  
**Prerequisites:** v0.4 complete, security audit  

### Goals

**Enterprise safety controls:**
- [ ] Mandatory `scan_unsafe()` on all outputs (no bypass except in sandboxed eval mode)
- [ ] `SECURITY.md` covers: threat model, redaction guarantees, LLM isolation, audit trail
- [ ] Pre-release security audit of LLM integration
- [ ] Vulnerability disclosure process

**Case management:**
- [ ] `storageops cases` subcommand: list, view, archive cases
- [ ] Case export: JSON (machine-readable), Markdown (human-readable), PDF (via pandoc)
- [ ] Case tagging and search

**BYOK and provider abstraction:**
- [ ] Stable `LLMProvider` interface supporting: Anthropic, OpenAI, Azure OpenAI, Ollama (local)
- [ ] Provider config in `~/.storageops/config.yaml` (never in code)
- [ ] Token budget management per case

**Plugin/tool boundary:**
- [ ] Published interface for adding new Skill Packs as separate packages
- [ ] Published interface for adding new parsers and analyzers as plugins
- [ ] Versioned Skill Pack API

**Observability:**
- [ ] `storageops audit` subcommand: replay and inspect any past session
- [ ] Prometheus metrics endpoint (optional, off by default)
- [ ] Structured JSON logging throughout

**Distribution:**
- [ ] Published to PyPI: `pip install storageops`
- [ ] GitHub Releases with signed artifacts
- [ ] Docker image: `ghcr.io/hxddh/storageops:1.0`

### Deliverables

- Published to PyPI
- Security audit completed and findings resolved
- Full audit trail for all agent sessions
- Plugin interface for Skill Packs
- Documentation site (MkDocs or similar)

---

## Summary Timeline

| Version | Focus | Weeks | Key Gate |
|---|---|---|---|
| v0.1 | Bug fixes + test infrastructure | 4 | pytest passes; eval --all works |
| v0.2 | Core stabilization + packaging | 6 | storageops-core installable; 9 domains covered |
| v0.3 | CLI reliability + docs | 6 | All README examples run; batch mode |
| v0.4 | Offline agent + LLM BYOK | 8 | LLM option works; audit log; case context |
| v1.0 | Production-ready | 12 | PyPI; security audit; plugin API |
