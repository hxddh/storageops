"""
LLM provider abstraction for StorageOps agent.

Supports:
  - Anthropic Claude (primary, default)
  - OpenAI-compatible APIs (OpenAI, Azure, local)
  - Ollama (local, no API key needed)

API keys are read from (priority order):
  1. Explicit argument to build_provider()
  2. Environment variable STORAGEOPS_LLM_KEY (or ANTHROPIC_API_KEY / OPENAI_API_KEY)
  3. ~/.storageops/config.yaml

NEVER hardcode API keys. NEVER commit config.yaml.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Retry helper ─────────────────────────────────────────────────────

_RATE_LIMIT_INDICATORS = (
    "429", "rate limit", "too many requests", "overloaded",
    "529", "capacity", "quota",
)


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(ind in msg for ind in _RATE_LIMIT_INDICATORS)


def _retry(fn: Any, max_retries: int = 3) -> Any:
    """Call fn(), retrying up to max_retries times on rate-limit errors."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries or not _is_rate_limit(exc):
                raise
            delay = 2 ** (attempt + 1)   # 2s, 4s, 8s
            time.sleep(delay)


@dataclass
class LLMResponse:
    content: str
    stop_reason: str          # "end_turn" | "tool_use" | "max_tokens"
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


# ── Anthropic ────────────────────────────────────────────────────────


class AnthropicProvider:
    """Anthropic Claude via the official SDK."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-8"):
        try:
            import anthropic as _anthropic
            self._anthropic = _anthropic
        except ImportError:
            raise ImportError(
                "anthropic package not installed. "
                "Run: pip install 'storageops[llm]' or pip install anthropic"
            )
        self._client = self._anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        on_text_chunk: Any = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        # Prompt caching: mark system prompt for caching (saves ~90% on repeated calls)
        if system:
            kwargs["system"] = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        # Cache the tool definitions (they're large and static per session)
        if tools:
            cached_tools = list(tools)
            if cached_tools:
                cached_tools = [dict(t) for t in cached_tools]
                cached_tools[-1] = dict(cached_tools[-1])
                cached_tools[-1]["cache_control"] = {"type": "ephemeral"}
            kwargs["tools"] = cached_tools

        def _do_stream():
            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    on_text_chunk(text)
                return stream.get_final_message()

        def _do_create():
            return self._client.messages.create(**kwargs)

        if on_text_chunk is not None:
            resp = _retry(_do_stream)
        else:
            resp = _retry(_do_create)

        text_parts = [b.text for b in resp.content if hasattr(b, "text")]
        tool_calls = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in resp.content
            if b.type == "tool_use"
        ]
        usage = resp.usage
        return LLMResponse(
            content="\n".join(text_parts),
            stop_reason=resp.stop_reason,
            tool_calls=tool_calls,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )


# ── OpenAI-compatible ─────────────────────────────────────────────────


class OpenAICompatProvider:
    """OpenAI-compatible provider (OpenAI, Azure OpenAI, local LLMs via LiteLLM etc.)."""

    def __init__(self, api_key: str, base_url: str, model: str):
        try:
            from openai import OpenAI as _OpenAI
            self._client = _OpenAI(api_key=api_key, base_url=base_url)
        except ImportError:
            raise ImportError(
                "openai package not installed. "
                "Run: pip install 'storageops[llm-openai]' or pip install openai"
            )
        self.model = model

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        on_text_chunk: Any = None,
    ) -> LLMResponse:
        msgs = list(messages)
        if system:
            msgs = [{"role": "system", "content": system}] + msgs

        # Convert Anthropic-format messages to OpenAI format
        converted = []
        for msg in msgs:
            if isinstance(msg.get("content"), list):
                # Anthropic tool_use / tool_result blocks
                oai_msg = _convert_anthropic_msg_to_openai(msg)
                converted.extend(oai_msg)
            else:
                converted.append(msg)

        oai_tools = None
        if tools:
            oai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                }
                for t in tools
            ]

        if on_text_chunk is not None and not oai_tools:
            def _do_stream():
                stream = self._client.chat.completions.create(
                    model=self.model, messages=converted,
                    max_tokens=max_tokens, stream=True,
                )
                full_content = ""
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        on_text_chunk(delta)
                        full_content += delta
                return full_content
            content = _retry(_do_stream)
            return LLMResponse(content=content, stop_reason="end_turn")

        resp = _retry(lambda: self._client.chat.completions.create(
            model=self.model,
            messages=converted,
            tools=oai_tools,
            max_tokens=max_tokens,
        ))

        choice = resp.choices[0]
        content = choice.message.content or ""
        stop_reason = "end_turn"
        tool_calls = []

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            stop_reason = "tool_use"
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments),
                }
                for tc in choice.message.tool_calls
            ]

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
        )


def _convert_anthropic_msg_to_openai(msg: dict) -> list[dict]:
    """Convert a single Anthropic-format message to one or more OpenAI messages."""
    role = msg["role"]
    content = msg["content"]

    if role == "assistant":
        text_parts = [b["text"] for b in content if b.get("type") == "text"]
        tool_calls = [
            {
                "id": b["id"],
                "type": "function",
                "function": {
                    "name": b["name"],
                    "arguments": json.dumps(b["input"]),
                },
            }
            for b in content
            if b.get("type") == "tool_use"
        ]
        oai_msg: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts)}
        if tool_calls:
            oai_msg["tool_calls"] = tool_calls
        return [oai_msg]

    elif role == "user":
        # Could be tool_result blocks
        tool_results = [b for b in content if b.get("type") == "tool_result"]
        text_blocks = [b for b in content if b.get("type") != "tool_result"]

        result_msgs = []
        for tr in tool_results:
            result_msgs.append({
                "role": "tool",
                "tool_call_id": tr["tool_use_id"],
                "content": tr.get("content", ""),
            })
        if text_blocks or not tool_results:
            text = "\n".join(
                b.get("text", str(b)) for b in text_blocks
            ) if text_blocks else (msg.get("content") or "")
            result_msgs.insert(0, {"role": "user", "content": text})
        return result_msgs

    return [msg]


# ── Ollama ────────────────────────────────────────────────────────────


class OllamaProvider:
    """Local Ollama provider — no API key required."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str = "",
        max_tokens: int = 4096,
        on_text_chunk: Any = None,
    ) -> LLMResponse:
        msgs = list(messages)
        if system:
            msgs = [{"role": "system", "content": system}] + msgs

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = tools

        data = json.dumps(payload).encode()

        def _do_request():
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())

        result = _retry(_do_request)

        content = result.get("message", {}).get("content", "")
        tool_calls = []
        stop_reason = "end_turn"

        raw_tc = result.get("message", {}).get("tool_calls", [])
        if raw_tc:
            stop_reason = "tool_use"
            for tc in raw_tc:
                fn = tc.get("function", {})
                tool_calls.append({
                    "id": f"ollama_{fn.get('name', 'tool')}_{len(tool_calls)}",
                    "name": fn.get("name", ""),
                    "input": fn.get("arguments", {}),
                })

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
        )


# ── Factory ───────────────────────────────────────────────────────────


def _load_config() -> dict:
    """Load ~/.storageops/config.yaml if present."""
    config_path = Path.home() / ".storageops" / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml  # type: ignore[import]
        return yaml.safe_load(config_path.read_text()) or {}
    except ImportError:
        # Minimal key:value parsing without yaml dep
        conf: dict = {}
        for line in config_path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and ":" in stripped:
                k, _, v = stripped.partition(":")
                conf[k.strip()] = v.strip().strip('"').strip("'")
        return conf


def build_provider(
    provider_name: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> AnthropicProvider | OpenAICompatProvider | OllamaProvider:
    """
    Build a provider instance.

    Config priority: explicit arg > env var > ~/.storageops/config.yaml
    """
    cfg = _load_config()

    key = (
        api_key
        or os.environ.get("STORAGEOPS_LLM_KEY")
        or cfg.get("llm_api_key", "")
    )

    if provider_name == "anthropic":
        m = model or os.environ.get("STORAGEOPS_LLM_MODEL") or cfg.get(
            "llm_model", "claude-opus-4-8"
        )
        if not key:
            key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError(
                "Anthropic API key required.\n"
                "Set ANTHROPIC_API_KEY env var, or STORAGEOPS_LLM_KEY, "
                "or add llm_api_key to ~/.storageops/config.yaml"
            )
        return AnthropicProvider(api_key=key, model=m)

    elif provider_name in ("openai", "azure", "openai-compatible"):
        m = model or cfg.get("llm_model", "gpt-4o")
        url = base_url or cfg.get("llm_base_url", "https://api.openai.com/v1")
        if not key:
            key = os.environ.get("OPENAI_API_KEY", "")
        return OpenAICompatProvider(api_key=key, base_url=url, model=m)

    elif provider_name == "ollama":
        m = model or cfg.get("llm_model", "llama3.2")
        url = base_url or cfg.get("llm_base_url", "http://localhost:11434")
        return OllamaProvider(base_url=url, model=m)

    else:
        raise ValueError(
            f"Unknown provider: {provider_name!r}. "
            "Supported: anthropic, openai, openai-compatible, ollama"
        )
