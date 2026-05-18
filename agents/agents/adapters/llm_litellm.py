"""LiteLLM LLMProvider adapter — the default.

Speaks to 100+ providers (Claude, OpenAI, Gemini, Mistral, Cohere, Ollama,
vLLM, ...) through a single API. Cost tracking + fallback chains built in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import Config
from ..ports import (
    ChatResponse,
    LLMProvider,
    Message,
    Tool,
    ToolCall,
    Vector,
)

if TYPE_CHECKING:
    pass


class LiteLLMAdapter:
    """LiteLLM-backed LLM provider.

    Configuration (from agents/config.yml):
        litellm:
          model: claude-sonnet-4-6
          fallback_models: [gpt-4o, gemini-2.5-pro]
          api_key_secret: ANTHROPIC_API_KEY
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        fallback_models: list[str] | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._fallbacks = fallback_models or []
        # Lazy import — keep adapter file the only consumer of the SDK
        import litellm  # type: ignore[import-untyped]
        self._litellm = litellm

    @classmethod
    def from_config(cls, config: Config) -> "LiteLLMAdapter":
        from .secrets_envvar import EnvVarSecretStore   # bootstrap order: ok
        secrets = EnvVarSecretStore()
        litellm_cfg = config.extras.get("litellm", {})
        api_key_name = litellm_cfg.get("api_key_secret", "ANTHROPIC_API_KEY")
        return cls(
            model=litellm_cfg.get("model", "claude-sonnet-4-6"),
            api_key=secrets.get_or_raise(api_key_name),
            fallback_models=litellm_cfg.get("fallback_models", []),
        )

    def chat(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        tools: list[Tool] | None = None,
        stop_sequences: list[str] | None = None,
    ) -> ChatResponse:
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict[str, Any] = {
            "model": model or self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "api_key": self._api_key,
        }
        if tools:
            kwargs["tools"] = [{
                "type": "function",
                "function": {
                    "name": t.name, "description": t.description,
                    "parameters": t.input_schema,
                },
            } for t in tools]
        if stop_sequences:
            kwargs["stop"] = stop_sequences
        if self._fallbacks:
            kwargs["fallbacks"] = self._fallbacks

        resp = self._litellm.completion(**kwargs)
        choice = resp.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        for tc in (getattr(message, "tool_calls", None) or []):
            tool_calls.append(ToolCall(
                id=tc.id, name=tc.function.name,
                arguments=_safe_json(tc.function.arguments),
            ))

        usage = getattr(resp, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
        tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
        # LiteLLM exposes cost via resp._hidden_params on some versions:
        cost = float(getattr(resp, "_response_cost", 0.0) or 0.0)

        finish_map = {
            "stop": "stop", "length": "length", "tool_calls": "tool_use",
            "content_filter": "content_filter",
        }
        return ChatResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            model=resp.model,
            finish_reason=finish_map.get(choice.finish_reason, "stop"),
        )

    def embed(self, texts: list[str], *, model: str | None = None) -> list[Vector]:
        resp = self._litellm.embedding(
            model=model or "text-embedding-3-large",
            input=texts,
            api_key=self._api_key,
        )
        return [d["embedding"] for d in resp.data]

    @property
    def name(self) -> str:
        return self._model

    @property
    def cost_per_1k_input_usd(self) -> float:
        # LiteLLM tracks cost dynamically via _response_cost; this is a static
        # fallback for budgeting heuristics. Real cost reported per call.
        return 0.003   # Claude Sonnet rough rate; adapter user can override

    @property
    def cost_per_1k_output_usd(self) -> float:
        return 0.015


def _safe_json(s: str) -> dict:
    import json
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": s}


_ = LLMProvider  # Protocol check
