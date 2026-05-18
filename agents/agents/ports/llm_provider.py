"""LLMProvider port — chat and embed calls, vendor-agnostic.

Default adapter: LiteLLM (supports 100+ providers).
Direct adapters: Claude, OpenAI, Gemini, Ollama.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

Vector = list[float]


@dataclass(frozen=True)
class Message:
    """A chat message. Roles map across providers via the adapter."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None          # for tool messages
    tool_call_id: str | None = None  # for tool responses


@dataclass(frozen=True)
class Tool:
    """A tool/function declaration."""

    name: str
    description: str
    input_schema: dict[str, Any]     # JSON Schema


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatResponse:
    content: str
    tool_calls: list[ToolCall]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str
    finish_reason: Literal["stop", "tool_use", "length", "content_filter"]


class LLMProvider(Protocol):
    """Vendor-agnostic LLM interface.

    Implementations live in agents/adapters/llm_*.py. Each adapter translates
    these calls into the provider's specific shape. The Tool and ChatResponse
    types are stable — adapters do the conversion.
    """

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
        """Single-shot chat completion. Returns a normalised response."""
        ...

    def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[Vector]:
        """Batch embed. Returns one vector per input text."""
        ...

    @property
    def name(self) -> str:
        """Canonical model identifier — e.g. 'claude-sonnet-4-6', 'gpt-4o'."""
        ...

    @property
    def cost_per_1k_input_usd(self) -> float:
        """USD cost per 1000 input tokens. Used for budget tracking."""
        ...

    @property
    def cost_per_1k_output_usd(self) -> float:
        """USD cost per 1000 output tokens."""
        ...
