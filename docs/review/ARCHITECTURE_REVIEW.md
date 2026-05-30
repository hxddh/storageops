# Architecture Review

**Review Date:** 2026-05-30  
**Scope:** Overall project architecture, layer boundaries, dependency structure, packaging

---

## 1. Intended Architecture (from README / AGENTS.md)

```
Skill Pack (agents/skills/)
    └── guides LLM agent behavior (SKILL.md, references/, templates/)
storageops-core (Python library)
    ├── parsers/        parse raw log/config text → structured JSON
    ├── analyzers/      structured JSON → findings + recommendations
    ├── utils/          secret scanner, shared helpers
    └── tests/          smoke tests
storageops-cli (Python CLI)
    ├── triage          classify input domain
    ├── analyze         run parsers + analyzers
    ├── report          format output as Markdown
    ├── eval            score output against golden cases
    └── agent           orchestrate multi-step diagnosis
```

This is a clean, layered design: Skills guide behavior → Core provides deterministic analysis → CLI exposes it → Agent orchestrates.

---

## 2. Verified Facts

### 2.1 Dependency isolation is correct
- `storageops-core/` has zero external dependencies (stdlib only). **Verified** by `pyproject.toml` in `storageops-cli/` showing `dependencies = []` and no `requirements.txt` anywhere.
- No `import boto3`, `import botocore`, `import google.cloud`, `import requests`, or any cloud SDK exists in any production `.py` file. **Verified** by grep.
- No `subprocess`, `os.system`, or `os.exec*` calls in production code. **Verified** by grep.

### 2.2 Parsers are deterministic and text-only
All parsers in `storageops-core/parsers/` accept a plain `str` argument and return a `dict`. No I/O, no network, no subprocess. **Verified** by reading all 6 parser files.

### 2.3 Zero-network guarantee holds
Neither the parsers, analyzers, nor CLI make any outbound network calls. This satisfies the "offline-first" design goal. **Verified** by code inspection.

---

## 3. Architecture Problems

### 3.1 storageops-core is not a proper Python package (P1)

**Evidence:**
- `storageops-core/parsers/`, `storageops-core/analyzers/`, `storageops-core/utils/` have **no `__init__.py`**.
- `storageops-core/` itself has no `pyproject.toml` or `setup.py`.
- All consumers (`cli.py`, `agent.py`, `run_validation.py`, `smoke_test.py`) import via `sys.path` mutation:
  ```python
  sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'storageops-core', 'parsers'))
  sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'storageops-core', 'analyzers'))
  ```
- This means `storageops-core` cannot be `pip install`-ed separately, cannot be referenced by a virtual environment without `sys.path` manipulation, and breaks standard IDE tooling (linters, type checkers).

**Impact:** Any future consumer of `storageops-core` (a web service, a notebook, another CLI) must replicate the same `sys.path` hack.

**Recommendation:** Add `__init__.py` to each sub-package and add a `pyproject.toml` to `storageops-core/` so it can be installed as `pip install -e storageops-core/`.

---

### 3.2 Agent layer conflates "LLM agent" with "rule-based orchestrator" (P1)

**Evidence:**
- `storageops-cli/storageops/agent.py` contains no LLM API calls, no model imports, no prompt templates.
- The "agent loop" is: route to domain → check hardcoded evidence checklist → run deterministic analyzer → format report.
- `max_turns = 5` is present but the loop does not perform actual multi-turn reasoning — each "turn" is a fixed pipeline stage.
- README and AGENTS.md use "agent" and "AI" language that implies LLM capability.

**Impact:** Users and developers reading the documentation expect adaptive, multi-turn LLM behavior and will be surprised by the actual rule-based implementation.

**Recommendation:** Either (a) rename `storageops agent` to `storageops diagnose` and document it as "offline deterministic diagnostic engine" or (b) clearly add a "Current Implementation" section to README explaining the distinction between the current rule engine and the planned LLM agent.

---

### 3.3 Evidence checklists are hardcoded and duplicated (P2)

**Evidence:**
- `agent.py` contains `EVIDENCE_CHECKLIST` dict with per-domain checklists (lines ~60-140).
- The same information exists in the `SKILL.md` files under `agents/skills/`.
- The two sources have diverged in granularity and wording.

**Impact:** When a Skill is updated, the agent's hardcoded checklist does not update. This creates a maintenance split.

**Recommendation:** Define the canonical evidence checklist in `skill-registry.yaml` or a separate `evidence-schema.yaml` and load it programmatically in both the agent and the Skills.

---

### 3.4 network_endpoint_access analyzer is a stub (P1)

**Evidence:**
- `storageops-cli/storageops/cli.py`: The `analyze` command dispatches to analyzer modules for most domains, but for `network_endpoint_access` it returns a hardcoded stub dict:
  ```python
  result = {"domain": "network_endpoint_access", "status": "manual_investigation_required", ...}
  ```
- The `storageops-network-endpoint-access` Skill has a full `SKILL.md` and 5 reference documents, but there is no corresponding analyzer in `storageops-core/analyzers/`.

**Impact:** The network/endpoint skill is the most common first-line diagnosis for "can't connect" issues. Having it return only a manual investigation stub means the CLI provides no value for this entire problem class.

**Recommendation:** Implement `analyze_network_endpoint.py` covering: DNS resolution failures, endpoint routing patterns, TLS errors, MTU issues. Reference `agents/skills/storageops-network-endpoint-access/references/` for the content.

---

### 3.5 parse_s5cmd_log.py exists but is unused in the agent (P2)

**Evidence:**
- `storageops-core/parsers/parse_s5cmd_log.py` exists and is used in `cmd_analyze()` for the `performance_throughput` branch.
- `agent.py`'s `run_analysis()` function does NOT call `parse_s5cmd_log` for any domain. The agent cannot process s5cmd logs.
- `storageops-cli-sdk-diagnosis` Skill has a full `references/s5cmd.md` reference document.

**Recommendation:** Wire `parse_s5cmd_log` into the agent's `run_analysis()` for the `s3_protocol_compatibility` and `cli_sdk_diagnosis` domains.

---

### 3.6 Skill registry is informational only — no enforcement (P3)

**Evidence:**
- `skill-registry.yaml` declares `routes`, `priority`, and `auto_route` fields per skill.
- No code in `cli.py` or `agent.py` reads `skill-registry.yaml`.
- Routing logic in `agent.py` (`auto_detect()` and `DOMAIN_SKILL_MAP`) is hardcoded independently.

**Impact:** If a new Skill is added to `skill-registry.yaml` without updating the hardcoded maps in `agent.py`, the new skill is never invoked by the agent.

**Recommendation:** Make `agent.py` load routing configuration from `skill-registry.yaml` at startup rather than maintaining a parallel hardcoded copy.

---

## 4. Architecture Strengths

- **Zero external dependencies in core** — excellent; makes it trivially portable
- **Parser/analyzer separation** — parsers produce structured facts; analyzers consume them; clean boundary
- **Offline-first by design** — no cloud API calls in any production path
- **Evidence-based output contract** — parsers consistently return `ok`, `module`, and structured evidence fields
- **Skill Pack as LLM guidance layer** — the separation between Skills (LLM guidance) and Core (deterministic analysis) is architecturally sound and well-thought-out

---

## 5. Architecture Recommendations Summary

| Priority | Recommendation | Effort |
|---|---|---|
| P1 | Add `__init__.py` + `pyproject.toml` to `storageops-core` | Small (2h) |
| P1 | Rename/re-document `storageops agent` as rule-based | Small (1h docs) |
| P1 | Implement `analyze_network_endpoint.py` | Medium (1-2d) |
| P2 | Load skill routing from `skill-registry.yaml` | Medium (4h) |
| P2 | Centralize evidence checklists in registry | Medium (4h) |
| P2 | Wire `parse_s5cmd_log` into agent domains | Small (2h) |
