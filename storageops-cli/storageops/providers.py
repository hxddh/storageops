"""
LLM Provider adapter.

Supports:
    openai      — Any OpenAI-compatible API (OpenAI, Azure, local proxies)
    anthropic   — Anthropic Claude API
    ollama      — Local Ollama server

API key: read from environment variable only, never from CLI args.

Usage:
    from providers import chat, get_default_model

    response = chat(
        provider="openai",
        model="gpt-4o-mini",
        system_prompt="You are a storage diagnostic expert.",
        messages=[{"role": "user", "content": "..."}],
        tools=[...],
    )
"""
import json
import os
import urllib.request
import urllib.error


# ── Model defaults per provider ──────────────────────────────────────

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "ollama": "qwen2.5:14b",
}

API_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "ollama": "http://localhost:11434/v1",  # Ollama serves OpenAI-compatible API
}


def get_api_key(provider: str) -> str:
    """Resolve API key from environment."""
    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ollama": None,  # No key needed
    }
    env_var = env_map.get(provider)
    if env_var is None:
        return ""
    key = os.environ.get(env_var, "")
    if not key:
        raise RuntimeError(
            f"{provider} API key not found. Set {env_var} environment variable.\n"
            f"  export {env_var}='sk-...'"
        )
    return key


def get_default_model(provider: str) -> str:
    return DEFAULT_MODELS.get(provider, "gpt-4o-mini")


def chat(provider: str, model: str, system_prompt: str,
         messages: list, tools: list = None, tool_choice: str = "auto",
         temperature: float = 0.1, max_tokens: int = 4096) -> dict:
    """
    Send a chat completion request. Returns OpenAI-format response dict
    with choices[0].message (content + optional tool_calls).
    """
    if provider == "ollama":
        # Ollama OpenAI-compatible API
        return _chat_openai_compatible(
            base_url=API_BASE_URLS["ollama"],
            api_key="ollama",  # Ollama ignores auth
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "openai":
        return _chat_openai_compatible(
            base_url=API_BASE_URLS["openai"],
            api_key=get_api_key("openai"),
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    elif provider == "anthropic":
        return _chat_anthropic(
            api_key=get_api_key("anthropic"),
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ── OpenAI-compatible (OpenAI, Ollama, proxies) ────────────────────

def _chat_openai_compatible(base_url: str, api_key: str, model: str,
                            system_prompt: str, messages: list,
                            tools: list, tool_choice: str,
                            temperature: float, max_tokens: int) -> dict:
    """Send request to OpenAI-compatible API."""
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else str(e)
        raise RuntimeError(f"API error {e.code}: {body[:500]}") from e


# ── Anthropic (Messages API, translated to OpenAI format) ──────────

def _chat_anthropic(api_key: str, model: str, system_prompt: str,
                    messages: list, tools: list,
                    temperature: float, max_tokens: int) -> dict:
    """
    Call Anthropic Messages API, convert response to OpenAI-compatible format
    so the agent loop doesn't need to know the difference.
    """
    import uuid

    url = "https://api.anthropic.com/v1/messages"

    # Convert tools to Anthropic format
    anthropic_tools = None
    if tools:
        anthropic_tools = []
        for t in tools:
            if t.get("type") == "function":
                func = t["function"]
                anthropic_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system_prompt}],
        "messages": [_to_anthropic_message(m) for m in messages],
        "temperature": temperature,
    }
    if anthropic_tools:
        payload["tools"] = anthropic_tools

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Convert Anthropic response to OpenAI format
        content = data.get("content", [])
        text_parts = []
        tool_calls = []

        for block in content:
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        return {
            "id": data.get("id", ""),
            "object": "chat.completion",
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                    "tool_calls": tool_calls if tool_calls else None,
                },
                "finish_reason": data.get("stop_reason", "stop"),
            }],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (data.get("usage", {}).get("input_tokens", 0) +
                                data.get("usage", {}).get("output_tokens", 0)),
            },
        }

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else str(e)
        raise RuntimeError(f"Anthropic API error {e.code}: {body[:500]}") from e


def _to_anthropic_message(msg: dict) -> dict:
    """Convert OpenAI-format message to Anthropic format."""
    role = msg.get("role", "user")
    content = msg.get("content", "")

    # Handle tool results
    if role == "tool":
        # Anthropic expects tool_result as user message
        tool_call_id = msg.get("tool_call_id", "")
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": content,
            }],
        }

    # Handle assistant tool_calls
    if role == "assistant" and msg.get("tool_calls"):
        parts = [{"type": "text", "text": content}] if content else []
        for tc in msg["tool_calls"]:
            func = tc.get("function", {})
            parts.append({
                "type": "tool_use",
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "input": json.loads(func.get("arguments", "{}")),
            })
        return {"role": "assistant", "content": parts}

    # Plain message
    return {"role": role, "content": content if isinstance(content, str)
            else json.dumps(content)}
