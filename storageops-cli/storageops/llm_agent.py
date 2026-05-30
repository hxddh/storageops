"""
LLM-powered StorageOps diagnostic agent.

Implements a ReAct loop (Reason + Act):
  1. Evidence text is secret-scanned and wrapped in <user_evidence> XML.
  2. System prompt is built from SKILL.md + safety rules.
  3. LLM reasons and calls tools to gather structured evidence.
  4. Each tool result is secret-scanned before being returned to LLM context.
  5. When LLM produces a final answer, it passes through the unsafe output gate.
  6. Every LLM call and tool invocation is logged to ~/.storageops/audit.jsonl.

Evidence-first: rule-based parsers produce structured JSON before the LLM
reasons about findings. Raw log text stays in the <user_evidence> envelope.
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

# Ensure storageops-core is importable
_CLI_DIR = Path(__file__).parent.parent
_CORE_DIR = _CLI_DIR.parent / "storageops-core"
for _sub in ("utils", "parsers", "analyzers"):
    _p = str(_CORE_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from secret_scanner import scan as _scan_secrets  # noqa: E402

from storageops.llm_provider import LLMResponse, build_provider  # noqa: E402
from storageops.tool_registry import TOOL_DEFINITIONS, dispatch_tool  # noqa: E402
from storageops.prompt_builder import build_system_prompt, build_initial_message  # noqa: E402
from storageops import audit_logger  # noqa: E402


# ── Unsafe output gate ────────────────────────────────────────────────

_UNSAFE_PATTERNS = [
    (r'delete\s+(?:the\s+)?bucket', 'delete_bucket'),
    (r'make\s+(?:the\s+)?(?:bucket|it)\s+public', 'make_public'),
    (r'print\s+(?:the\s+)?access\s+key', 'print_credentials'),
    (r'--no-verify-ssl', 'disable_tls'),
    (r'"Principal"\s*:\s*"\*"', 'wildcard_principal'),
    (r'disable\s+block\s+public\s+access', 'disable_block_public_access'),
    (r'rm\s+-rf\s+.*s3://', 'destructive_delete'),
]


def _check_unsafe(text: str) -> list[str]:
    """Return unsafe pattern names found, skipping manual-only annotated lines."""
    findings = []
    for line in text.splitlines():
        stripped = line.strip()
        if "# manual-only:" in stripped or stripped.startswith("# manual-only"):
            continue
        for pattern, name in _UNSAFE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append(name)
    return findings


class UnsafeOutputError(Exception):
    pass


# ── Message helpers ───────────────────────────────────────────────────

def _assistant_msg(response: LLMResponse) -> dict:
    """Build Anthropic-format assistant message from LLMResponse."""
    content = []
    if response.content:
        content.append({"type": "text", "text": response.content})
    for tc in response.tool_calls:
        content.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": tc["name"],
            "input": tc["input"],
        })
    return {"role": "assistant", "content": content}


def _tool_result_msg(tool_use_id: str, result_json: str) -> dict:
    """Build Anthropic-format tool result user message."""
    return {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result_json,
        }],
    }


# ── Main agent loop ───────────────────────────────────────────────────

def run_llm_agent(
    evidence_text: str,
    domain: str,
    provider_name: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    max_turns: int = 8,
    verbose: bool = False,
) -> dict:
    """
    Run the LLM diagnostic agent.

    Returns:
        {
            "report": str,              Markdown diagnostic report
            "domain": str,
            "turns_used": int,
            "session_id": str,
            "tool_calls_made": list[str],
            "secrets_redacted": int,
            "ok": bool,
        }
    """
    session_id = str(uuid.uuid4())[:8]

    # ── Pre-process: secret scan the input ───────────────────────────
    input_scan = _scan_secrets(evidence_text)
    if input_scan["count"] > 0:
        evidence_text = input_scan["redacted_text"]
        if verbose:
            print(
                f"  ⚠️  Redacted {input_scan['count']} secret(s) from input",
                file=sys.stderr,
            )

    # ── Build provider and context ───────────────────────────────────
    provider = build_provider(provider_name, api_key=api_key, model=model, base_url=base_url)
    provider_model = getattr(provider, "model", provider_name)

    audit_logger.log_session_start(session_id, domain, f"{provider_name}/{provider_model}")

    system_prompt = build_system_prompt(domain)
    initial_msg = build_initial_message(evidence_text, domain)
    messages: list[dict] = [{"role": "user", "content": initial_msg}]

    tool_calls_made: list[str] = []
    turns_used = 0

    try:
        for turn in range(max_turns):
            turns_used = turn + 1
            if verbose:
                print(f"\n  [LLM turn {turns_used}/{max_turns}]", file=sys.stderr)

            # ── Call LLM ─────────────────────────────────────────────
            response: LLMResponse = provider.complete(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                system=system_prompt,
                max_tokens=4096,
            )

            audit_logger.log_llm_call(
                session_id, turns_used, provider_name, provider_model,
                response.input_tokens, response.output_tokens, response.stop_reason,
            )

            # Append assistant turn
            messages.append(_assistant_msg(response))

            # ── Tool calls ───────────────────────────────────────────
            if response.stop_reason == "tool_use" and response.tool_calls:
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_input = tc["input"]

                    if verbose:
                        print(f"    → {tool_name}({list(tool_input.keys())})", file=sys.stderr)

                    audit_logger.log_tool_call(
                        session_id, turns_used, tool_name, list(tool_input.keys())
                    )
                    tool_calls_made.append(tool_name)

                    # Execute
                    result = dispatch_tool(tool_name, tool_input)
                    ok = "error" not in result
                    audit_logger.log_tool_result(
                        session_id, turns_used, tool_name, ok, result.get("error", "")
                    )

                    # Secret-scan the tool result before returning to LLM
                    result_json = json.dumps(result, ensure_ascii=False, default=str)
                    result_scan = _scan_secrets(result_json)
                    if result_scan["count"] > 0:
                        result_json = result_scan["redacted_text"]

                    messages.append(_tool_result_msg(tc["id"], result_json))

                continue  # next LLM turn with tool results in context

            # ── Final answer ─────────────────────────────────────────
            if response.stop_reason in ("end_turn", "stop"):
                final_text = response.content or ""

                # Secret-scan LLM output
                out_scan = _scan_secrets(final_text)
                if out_scan["count"] > 0:
                    final_text = out_scan["redacted_text"]
                    if verbose:
                        print(
                            f"  ⚠️  Redacted {out_scan['count']} secret(s) from LLM output",
                            file=sys.stderr,
                        )

                # Unsafe gate
                unsafe = _check_unsafe(final_text)
                if unsafe:
                    audit_logger.log_unsafe_output(session_id, turns_used, unsafe)
                    raise UnsafeOutputError(
                        f"LLM output blocked — unsafe patterns detected: {unsafe}"
                    )

                audit_logger.log_session_end(session_id, turns_used, "success")
                return {
                    "report": final_text,
                    "domain": domain,
                    "turns_used": turns_used,
                    "session_id": session_id,
                    "tool_calls_made": tool_calls_made,
                    "secrets_redacted": input_scan["count"],
                    "ok": True,
                }

            if response.stop_reason == "max_tokens":
                break

    except UnsafeOutputError as exc:
        audit_logger.log_session_end(session_id, turns_used, "unsafe_output_blocked")
        return {
            "report": str(exc),
            "domain": domain,
            "turns_used": turns_used,
            "session_id": session_id,
            "tool_calls_made": tool_calls_made,
            "ok": False,
            "error": "unsafe_output_blocked",
        }
    except Exception as exc:
        audit_logger.log_session_end(session_id, turns_used, f"error: {type(exc).__name__}")
        return {
            "report": f"Agent error ({type(exc).__name__}): {exc}",
            "domain": domain,
            "turns_used": turns_used,
            "session_id": session_id,
            "tool_calls_made": tool_calls_made,
            "ok": False,
            "error": str(exc),
        }

    audit_logger.log_session_end(session_id, turns_used, "max_turns_reached")
    return {
        "report": (
            "Maximum turns reached without a final answer. "
            "Please provide more specific evidence or increase --max-turns."
        ),
        "domain": domain,
        "turns_used": turns_used,
        "session_id": session_id,
        "tool_calls_made": tool_calls_made,
        "ok": False,
        "error": "max_turns_reached",
    }
