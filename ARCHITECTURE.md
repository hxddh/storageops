# Architecture

## Overview

StorageOps is a **Pi-powered diagnostic agent** with an **append-only session store**.
It's designed as a thin orchestration layer over Pi Coding Agent, delegating all LLM work
to Pi's subprocess RPC mode and all domain logic to deterministic parsers/analyzers.

```
┌─────────────────────────────────────────────────────────┐
│                      StorageOps                          │
│                                                         │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────┐  │
│  │    REPL     │   │   CLI       │   │  API Server  │  │
│  │  (repl.py)  │   │  (cli.py)   │   │(api_server)  │  │
│  └──────┬──────┘   └──────┬──────┘   └──────┬───────┘  │
│         │                 │                  │          │
│         └────────┬────────┴──────────────────┘          │
│                  ▼                                      │
│     ┌─────────────────────────┐                         │
│     │  Agent (agent.py)        │  converse()            │
│     │  Stateless loop          │  converse_one_shot()   │
│     └─────┬──────────────┬────┘                         │
│           │              │                              │
│           ▼              ▼                              │
│  ┌─────────────┐  ┌──────────────┐                     │
│  │  Session    │  │  Pi Runtime  │                     │
│  │ (session.py)│  │ (pi_runtime) │                     │
│  │             │  │              │                     │
│  │ JSONL +     │  │ Subprocess   │                     │
│  │ meta.json   │  │ RPC mode     │                     │
│  └─────────────┘  └──────┬───────┘                     │
│                          │                              │
│  ┌──────────────────────┐│                              │
│  │  Tools               ││                              │
│  │  (tool_registry.py)  │◀── Pi calls tools via        │
│  │                      │    extension bridge           │
│  │  ┌──────────────────┐│                               │
│  │  │ Parsers          ││  parse_rclone_log             │
│  │  │ (12 modules)     ││  parse_sigv4_error            │
│  │  │                  ││  parse_s5cmd_log ...          │
│  │  ├──────────────────┤│                               │
│  │  │ Analyzers        ││  analyze_policy               │
│  │  │ (10 modules)     ││  detect_throttling            │
│  │  │                  ││  analyze_throughput ...       │
│  │  ├──────────────────┤│                               │
│  │  │ Utils            ││  secret_scanner               │
│  │  │ (2 modules)      ││  signatures                   │
│  │  └──────────────────┘│                               │
│  └──────────────────────┘                               │
└─────────────────────────────────────────────────────────┘

External: Pi Coding Agent binary (pi) — subprocess RPC mode
External: LLM provider (DeepSeek / Anthropic / OpenAI)
```

## Layer Design

### Engine Layer (session, agent, pi_runtime)

The **only three files that can change state**.

**Session** (`session.py`): append-only JSONL event log + sidecar meta.json.
- One `<uuid>.jsonl` per session — first line is type:"session" header
- One `<uuid>.meta.json` per session — id, name, summary, turns, provider, model
- JSONL is NEVER read-then-rewritten. Only appended.
- meta.json is atomically rewritten after each turn.
- Replay rebuilds conversation history from raw Pi events — no memory cache.

**Agent** (`agent.py`): stateless `converse(session, user_input, display)` function.
- Writes user_turn event → builds prompt → streams Pi events → handles tool calls → syncs meta.
- No class, no global state, no mode switching. Session IS the state.

**Pi Runtime** (`pi_runtime.py`): Pi subprocess manager.
- Starts Pi in RPC mode, sends prompts via stdin, reads events from stdout.
- Non-blocking I/O with `O_NONBLOCK` + `EAGAIN` for multi-turn support.
- Auto-wraps YAML config header for provider/model/api-key.
- Handles tool call/result lifecycle via stdin/stdout protocol.

### Interaction Layer (context, display, repl, picker)

Pure presentation — no state mutations.

**Context** (`context.py`): prompt construction functions.
- `build_prompt(session, user_input)`: identity + tools + replay + request.
- `compact_history()`: drops oldest turns to fit token budget.

**Display** (`display.py`): ANSI terminal rendering.
- Thinking output (dim grey), text deltas (normal), tool calls (yellow), results (green).

**REPL** (`repl.py`): interactive loop with slash commands.
- `/resume [id]`, `/history`, `/clear`, `/session`, `/search`, `/fork`, `$`, `@file`.

**Picker** (`picker.py`): interactive session selector with fuzzy search.

### CLI Layer (cli.py)

All CLI subcommands in one file. Delegates to engine and diagnostics.

### Tools Layer (tool_registry, action_tools, tool_bridge)

Deterministic parsers and analyzers. Zero LLM involvement.
- 21 tool definitions, dispatched by name.
- Pi extension bridge (`tool_bridge.py`) provides stdin/stdout interface.

## Session Design

```
~/.storageops/sessions/
├── 019e80fa-7ec0-789d-8cec-4cb2ad846351.jsonl     ← append-only event log
└── 019e80fa-7ec0-789d-8cec-4cb2ad846351.meta.json  ← sidecar metadata
```

**Event flow** (JSONL):
```jsonl
{"type":"session","id":"<uuid>","timestamp":"<iso>","cwd":"..."}
{"type":"user_turn","text":"rclone keeps failing with ETag mismatch"}
{"type":"response","command":"prompt","success":true}
{"type":"agent_start"}
{"type":"turn_start"}
{"type":"message_start","message":{"role":"user","content":[...]}}
{"type":"message_end","message":{"role":"user",...}}
{"type":"message_start","message":{"role":"assistant","content":[],"api":"openai-completions",...}}
{"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"..."}}
...
{"type":"turn_end","message":{"role":"assistant",...}}
{"type":"agent_end","messages":[...]}
```

Events are Pi's raw JSON — zero translation. Pi can add new event types without StorageOps changes.

**Replay**: extract user/assistant messages from JSONL events → build conversation string → inject into Pi prompt.

## Pi Integration

StorageOps uses Pi's **RPC mode** (`pi --rpc`). Communication via stdin/stdout:
- Send: `{"command":"prompt","text":"..."}` plus newline
- Receive: JSON events (agent_start, turn_start, message_start, message_update, turn_end, agent_end)
- Tool calls: Pi emits `toolCall` in message_update → StorageOps executes → sends `{"command":"tool_result","callId":"...","result":{...}}`

This means StorageOps never calls LLM APIs directly — it inherits all of Pi's provider support
(Anthropic, OpenAI, DeepSeek, Google, etc.).

## Skill System

14 skill packs in `agents/skills/` — each a Pi-compatible skill directory with:
- `SKILL.md` — skill prompt and instructions
- `references/` — domain knowledge (rclone.md, throttling.md, etc.)
- `scripts/` — auxiliary scripts

Skills are auto-discovered by Pi from the configured skills directory.

## Key Design Decisions

1. **Append-only session** — JSONL never rewritten. meta.json is disposable (reconstructible from JSONL).
2. **Pi events as raw JSON** — no custom event types, no translation layer. Pi is the protocol.
3. **Stateless agent** — `converse(session, input, display)`. No class, no mode flags.
4. **No mode switching** — model decides when to chat vs when to diagnose. One identity prompt.
5. **Flat package** — no nested `core/`, `ui/`, `cli/`, `runtime/` directories. Import depth ≤ 2.
6. **Deterministic tools** — all parsers/analyzers are pure functions. Zero network, zero side effects.
