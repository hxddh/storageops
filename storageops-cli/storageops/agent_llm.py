"""
LLM-powered diagnostic agent with tool-use loop.

Core cycle:
    LLM thinks → calls tool(s) → tool returns result → LLM thinks → ...
    → calls final_report → agent prints report and exits.

Fallback: if tool-use fails (model too weak / API error), auto-fallback
to v0.4 rule-based agent.
"""
import json
import sys
from pathlib import Path

CLI_DIR = Path(__file__).parent.parent
PROJECT_ROOT = CLI_DIR.parent
sys.path.insert(0, str(CLI_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from storageops.providers import chat, get_default_model
from storageops.prompt import build_system_prompt
from storageops.tools import TOOL_DEFINITIONS, call_tool, get_tool_schemas_for_domain

MAX_TOOL_TURNS = 8
MAX_ASK_TURNS = 3


def run(user_evidence: str, provider: str = "openai", model: str = None,
        verbose: bool = False) -> int:
    """
    Run the LLM agent diagnostic loop.

    Returns 0 on success, 1 on error.
    """
    if model is None:
        model = get_default_model(provider)

    system_prompt = build_system_prompt()
    messages = []
    ask_count = 0
    tools = TOOL_DEFINITIONS.copy()

    # Initial: provide the user's evidence
    messages.append({
        "role": "user",
        "content": f"Please diagnose the following object storage issue:\n\n```\n{user_evidence}\n```",
    })

    for turn in range(MAX_TOOL_TURNS):
        try:
            response = chat(
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
            )
        except Exception as e:
            if verbose:
                print(f"\n[LLM error] {e}", file=sys.stderr)
            _fallback_to_rules(user_evidence)
            return 0

        choice = response.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls") or []

        if verbose and content:
            print(f"\n[{provider}/{model}] {content[:200]}", file=sys.stderr)

        # ── No tool calls: LLM is asking a question or giving up ──
        if not tool_calls and content:
            if "final" in content.lower() or "report" in content.lower():
                print(content)
                return 0
            # LLM is asking the user for more info
            print(f"\n[Agent] {content}")
            if ask_count >= MAX_ASK_TURNS:
                print("[Agent] Maximum questions reached. Generating report with available evidence.")
                break
            user_reply = input("\n> ").strip()
            if not user_reply:
                print("[Agent] No response. Generating report with available evidence.")
                break
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": user_reply})
            ask_count += 1
            continue

        if not tool_calls:
            if verbose:
                print(f"\n[Agent] No tool calls and no content. Response: {json.dumps(response, indent=2)[:300]}", file=sys.stderr)
            _fallback_to_rules(user_evidence)
            return 0

        # ── Process tool calls ──
        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            if verbose:
                print(f"  [tool] {name}({json.dumps(args, ensure_ascii=False)[:120]})", file=sys.stderr)

            # final_report → print and exit
            if name == "final_report":
                report = args.get("report", "")
                print(report)
                return 0

            # Execute tool
            result = call_tool(name, args)
            if verbose:
                preview = result[:200] + ("..." if len(result) > 200 else "")
                print(f"  [result] {preview}", file=sys.stderr)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result,
            })

    # Max turns reached
    print("\n[Agent] Maximum analysis turns reached.")
    _fallback_to_rules(user_evidence)
    return 0


def _fallback_to_rules(evidence: str):
    """Fallback to the v0.4 rule-based agent if LLM fails."""
    print("\n[Agent] Falling back to rule-based diagnostic engine...\n")
    from storageops.agent import agent_run
    # Write evidence to temp file and run
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(evidence)
    try:
        agent_run(initial_file=f.name, interactive=False)
    finally:
        import os
        os.unlink(f.name)
