"""
LLM provider abstraction for StorageOps agent.

Supported providers (use --llm-provider or set the corresponding env var):

  Provider name      Env var               Default model
  ─────────────────  ────────────────────  ──────────────────────
  anthropic          ANTHROPIC_API_KEY      claude-opus-4-8
  openai             OPENAI_API_KEY         gpt-4o
  deepseek           DEEPSEEK_API_KEY       deepseek-chat
  moonshot           MOONSHOT_API_KEY       moonshot-v1-8k
  qwen               DASHSCOPE_API_KEY      qwen-max
  zhipu              ZHIPU_API_KEY          glm-4-plus
  groq               GROQ_API_KEY           llama-3.3-70b-versatile
  ollama             (none required)        llama3.2
  openai-compatible  STORAGEOPS_LLM_KEY     (set --llm-model)

Provider is auto-detected from the first env var found above — no need
to pass --llm-provider if only one key is set.

Key resolution order (per provider):
  1. --llm-key CLI flag
  2. Provider-specific env var (e.g. DEEPSEEK_API_KEY)
  3. STORAGEOPS_LLM_KEY (generic fallback)
  4. ~/.storageops/config.yaml → llm_key
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Provider presets ──────────────────────────────────────────────────
# Each entry: (env_var, base_url, default_model)

_PRESETS: dict[str, tuple[str, str, str]] = {
    "anthropic":   ("ANTHROPIC_API_KEY",  "",                                                  "claude-opus-4-8"),
    "openai":      ("OPENAI_API_KEY",     "https://api.openai.com/v1",                         "gpt-4o"),
    "deepseek":    ("DEEPSEEK_API_KEY",   "https://api.deepseek.com/v1",                       "deepseek-v3"),
    "moonshot":    ("MOONSHOT_API_KEY",   "https://api.moonshot.cn/v1",                        "kimi-k2.6"),
    "qwen":        ("DASHSCOPE_API_KEY",  "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max"),
    "zhipu":       ("ZHIPU_API_KEY",      "https://open.bigmodel.cn/api/paas/v4",              "glm-4.7"),
    "groq":        ("GROQ_API_KEY",       "https://api.groq.com/openai/v1",                    "llama-3.3-70b-versatile"),
}

# Providers that use the OpenAI-compatible client (all except anthropic and ollama)
_OPENAI_COMPAT = {"openai", "deepseek", "moonshot", "qwen", "zhipu", "groq", "openai-compatible"}

PROVIDER_NAMES = list(_PRESETS.keys()) + ["ollama", "openai-compatible"]


def auto_detect_provider() -> str | None:
    """Return the first provider whose env var is set, or None."""
    for name, (env_var, _, _) in _PRESETS.items():
        if os.environ.get(env_var):
            return name
    if os.environ.get("STORAGEOPS_LLM_KEY"):
        return "openai-compatible"
    return None


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
                "Run: pip install 'storageops[llm]'"
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
            cached_tools = [dict(t) for t in tools]
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
    """OpenAI-compatible provider — works for OpenAI, DeepSeek, Moonshot, Qwen, Zhipu, Groq, etc."""

    def __init__(self, api_key: str, base_url: str, model: str):
        try:
            from openai import OpenAI as _OpenAI
            self._client = _OpenAI(api_key=api_key, base_url=base_url)
        except ImportError:
            raise ImportError(
                "openai package not installed. "
                "Run: pip install 'storageops[llm]'"
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
                converted.extend(_convert_anthropic_msg_to_openai(msg))
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
        conf: dict = {}
        for line in config_path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and ":" in stripped:
                k, _, v = stripped.partition(":")
                conf[k.strip()] = v.strip().strip('"').strip("'")
        return conf


def build_provider(
    provider_name: str | None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> AnthropicProvider | OpenAICompatProvider | OllamaProvider:
    """
    Build an LLM provider instance.

    If provider_name is None, auto-detects from environment variables.
    Raises ValueError with a helpful message if no provider can be determined.
    """
    cfg = _load_config()

    # Auto-detect provider if not specified
    if provider_name is None:
        provider_name = auto_detect_provider() or cfg.get("llm_provider")
    if provider_name is None:
        env_list = "\n".join(
            f"  {env_var:<24} → {name}"
            for name, (env_var, _, _) in _PRESETS.items()
        )
        raise ValueError(
            "No LLM provider configured. Set one of these env vars:\n"
            + env_list
            + "\n\nOr pass --llm-provider explicitly."
        )

    # Resolve API key: explicit arg > provider env var > generic env var > config
    if not api_key:
        preset = _PRESETS.get(provider_name)
        if preset:
            api_key = os.environ.get(preset[0], "")
        api_key = api_key or os.environ.get("STORAGEOPS_LLM_KEY", "") or cfg.get("llm_key", "")

    # Resolve model
    resolved_model = model or os.environ.get("STORAGEOPS_LLM_MODEL") or cfg.get("llm_model")

    if provider_name == "anthropic":
        if not api_key:
            raise ValueError(
                "Anthropic API key not found.\n"
                "Set ANTHROPIC_API_KEY env var or add llm_key to ~/.storageops/config.yaml"
            )
        return AnthropicProvider(api_key=api_key, model=resolved_model or "claude-opus-4-8")

    elif provider_name == "ollama":
        url = base_url or cfg.get("llm_base_url", "http://localhost:11434")
        return OllamaProvider(base_url=url, model=resolved_model or "llama3.2")

    elif provider_name in _OPENAI_COMPAT:
        preset = _PRESETS.get(provider_name)
        default_base = preset[1] if preset else "https://api.openai.com/v1"
        default_model = preset[2] if preset else "gpt-4o"
        url = base_url or cfg.get("llm_base_url", default_base)
        m = resolved_model or default_model
        return OpenAICompatProvider(api_key=api_key or "", base_url=url, model=m)

    else:
        raise ValueError(
            f"Unknown provider: {provider_name!r}.\n"
            f"Supported: {', '.join(PROVIDER_NAMES)}"
        )
