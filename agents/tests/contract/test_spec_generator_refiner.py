"""Contract tests for spec_generator.refiner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agents.ports import ChatResponse
from agents.spec_generator import refiner

_BASE_DESIGN = """# X — Design Spec

## 1. Goal
Old goal.

## 2. Non-goals
- one

## 3. Tenancy impact
Per-tenant only.

## 4. Data model changes
None.

## 5. API surface
None.

## 6. Security model
Default ACL.

## 7. Test plan
TBD.

## 8. Rollout plan
TBD.

## 9. Observability
TBD.

## 10. Open questions
1. Confirm scope?
"""


@dataclass
class FakeLLM:
    payload: dict[str, Any] = field(default_factory=dict)
    raw_content: str | None = None
    calls: list[Any] = field(default_factory=list)

    def chat(self, messages, **_kw) -> ChatResponse:
        self.calls.append(messages)
        content = self.raw_content if self.raw_content is not None else json.dumps(self.payload)
        return ChatResponse(
            content=content, tool_calls=[],
            tokens_in=1, tokens_out=1, cost_usd=0.0,
            model="fake", finish_reason="stop",
        )

    def embed(self, texts, *, model=None):
        return [[0.0] * 4 for _ in texts]

    @property
    def name(self) -> str:
        return "fake"

    @property
    def cost_per_1k_input_usd(self) -> float:
        return 0.0

    @property
    def cost_per_1k_output_usd(self) -> float:
        return 0.0


def test_refiner_returns_normalised_record() -> None:
    updated = _BASE_DESIGN.replace("Old goal.", "New goal.")
    llm = FakeLLM(payload={
        "markdown": updated,
        "summary": "Replaced goal.",
        "remaining_questions": ["Should we ship in Q3?"],
        "confirmed": False,
    })
    out = refiner.refine(
        llm=llm,
        current_spec_md=_BASE_DESIGN,
        reporter_reply="The goal should be X instead.",
        kind="design",
    )
    assert "New goal." in out.markdown
    assert out.change_summary == "Replaced goal."
    assert out.remaining_questions == ("Should we ship in Q3?",)
    assert out.confirmed_signal is False


def test_refiner_falls_back_to_current_when_llm_drops_headings() -> None:
    """Defence-in-depth: if the LLM returns text that lost template headings,
    return the original markdown unchanged."""
    llm = FakeLLM(payload={
        "markdown": "Just a paragraph with no headings.",
        "summary": "Mangled.",
        "remaining_questions": [],
        "confirmed": False,
    })
    out = refiner.refine(
        llm=llm,
        current_spec_md=_BASE_DESIGN,
        reporter_reply="...",
        kind="design",
    )
    assert out.markdown == _BASE_DESIGN  # current preserved verbatim
    # The trailing newline is preserved so file writes stay consistent.


def test_refiner_tolerates_code_fenced_json() -> None:
    payload = {
        "markdown": _BASE_DESIGN,
        "summary": "No change.",
        "remaining_questions": [],
        "confirmed": False,
    }
    llm = FakeLLM(raw_content=f"```json\n{json.dumps(payload)}\n```")
    out = refiner.refine(
        llm=llm,
        current_spec_md=_BASE_DESIGN,
        reporter_reply="...",
        kind="design",
    )
    assert out.markdown.startswith("# X — Design Spec")


def test_refiner_truncates_overlong_summary() -> None:
    llm = FakeLLM(payload={
        "markdown": _BASE_DESIGN,
        "summary": "x" * 500,
        "remaining_questions": [],
        "confirmed": True,
    })
    out = refiner.refine(
        llm=llm, current_spec_md=_BASE_DESIGN, reporter_reply="...",
        kind="design",
    )
    assert len(out.change_summary) <= 200
    assert out.confirmed_signal is True
