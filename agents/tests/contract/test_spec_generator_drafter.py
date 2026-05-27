"""Contract tests for spec_generator.drafter.

These run a FAKE LLMProvider that returns a canned JSON section blob and
assert the drafter's deterministic rendering, slug derivation, and
template-completeness invariants (tenancy non-empty, ≥1 open question on
design specs).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from agents.ports import ChatResponse
from agents.spec_generator import drafter


@dataclass
class FakeLLM:
    """Returns whatever canned `payload` was injected."""

    canned: dict[str, str] = field(default_factory=dict)
    calls: list[Any] = field(default_factory=list)

    def chat(self, messages, *, model=None, max_tokens=4096,
             temperature=0.2, tools=None, stop_sequences=None) -> ChatResponse:
        self.calls.append(messages)
        return ChatResponse(
            content=json.dumps(self.canned),
            tool_calls=[],
            tokens_in=100,
            tokens_out=200,
            cost_usd=0.001,
            model="fake-model",
            finish_reason="stop",
        )

    def embed(self, texts, *, model=None):
        return [[0.0] * 4 for _ in texts]

    @property
    def name(self) -> str:
        return "fake-llm"

    @property
    def cost_per_1k_input_usd(self) -> float:
        return 0.0

    @property
    def cost_per_1k_output_usd(self) -> float:
        return 0.0


_TODAY = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)


def test_design_spec_rendered_in_template_order() -> None:
    llm = FakeLLM(canned={
        "goal": "Add a Fund Master page to Goliatt Contabilidad.",
        "non_goals": "- Does not change posting logic.\n- Does not migrate existing data.",
        "tenancy_impact": "No cross-tenant impact; the page is per-tenant scoped.",
        "data_model": "New model goliatt.fund.master with fields name/code/balance.",
        "api_surface": "REST GET /goliatt/funds; ORM goliatt.fund.master.search().",
        "security_model": "Standard ir.model.access; tenancy enforced by company_id.",
        "test_plan": "Unit: model CRUD. E2E: tour creates a fund.",
        "rollout_plan": "Behind feature flag goliatt.fund_master. Canary on tenant-1.",
        "observability": "Counter fund_master.create; alert if create-error > 5%.",
        "open_questions": "1. Should fund codes be auto-generated or user-entered?",
    })
    spec = drafter.draft(
        llm=llm,
        issue_number=126,
        issue_title="Maestro de Fuentes",
        issue_body="We need a Fund Master page in Contabilidad.",
        kind="design",
        today=_TODAY,
    )

    assert spec.kind == "design"
    assert spec.slug == "maestro-de-fuentes"
    assert spec.file_path == "docs/superpowers/specs/2026-05-27-maestro-de-fuentes-design.md"
    md = spec.markdown
    # Headings appear in the template's defined order
    assert md.index("## 1. Goal") < md.index("## 3. Tenancy impact")
    assert md.index("## 3. Tenancy impact") < md.index("## 10. Open questions")
    # Filled sections appear inline
    assert "Add a Fund Master page" in md
    assert "Standard ir.model.access" in md
    # Open questions parsed out of the section body
    assert spec.open_questions == ("Should fund codes be auto-generated or user-entered?",)


def test_design_spec_repairs_empty_tenancy_impact() -> None:
    """The drafter must not write a design spec with an empty tenancy section."""
    llm = FakeLLM(canned={
        "goal": "A thing.",
        "tenancy_impact": "",   # deliberately empty
        "open_questions": "1. Is this scoped to Contabilidad only?",
    })
    spec = drafter.draft(
        llm=llm,
        issue_number=42,
        issue_title="Some feature",
        issue_body="...",
        kind="design",
        today=_TODAY,
    )
    # The drafter back-fills a non-empty placeholder rather than emit an empty section.
    section_after = spec.markdown.split("## 3. Tenancy impact", 1)[1]
    body = section_after.split("## 4.", 1)[0].strip()
    assert len(body) >= 16, body


def test_design_spec_appends_default_question_when_missing() -> None:
    llm = FakeLLM(canned={
        "goal": "A thing.",
        "tenancy_impact": "No cross-tenant impact.",
        "open_questions": "Empty body with no question mark.",
    })
    spec = drafter.draft(
        llm=llm,
        issue_number=42,
        issue_title="Some feature",
        issue_body="...",
        kind="design",
        today=_TODAY,
    )
    assert any("?" in q for q in spec.open_questions) or "?" in spec.markdown.split(
        "## 10. Open questions",
    )[1]


def test_fix_brief_rendered_in_fix_template_order() -> None:
    llm = FakeLLM(canned={
        "symptom": "Search returns no results when filter is set.",
        "repro": "1. Open Catalog.\n2. Type 'foo'.\n3. Apply filter Category=Bar.",
        "affected_tenants": "All tenants with >100 items; severity medium.",
        "root_cause": "TBD — pending repro on agentlab.",
        "proposed_fix": "Replace `==` with `is None` check in search_filter.",
        "regression_test": "Hypothetical test: empty-string filter resolves to None.",
        "rollout": "Hotfix flow; cherry-pick to release.",
    })
    spec = drafter.draft(
        llm=llm,
        issue_number=200,
        issue_title="Search broken with filter",
        issue_body="Filter on category breaks search.",
        kind="fix",
        today=_TODAY,
    )
    assert spec.kind == "fix"
    assert spec.file_path.endswith("-fix.md")
    md = spec.markdown
    assert "Fix Brief" in md
    assert md.index("## 1. Symptom") < md.index("## 4. Root cause")
    # No "open questions" section in fix briefs
    assert "## 10. Open questions" not in md


def test_drafter_tolerates_code_fenced_json_response() -> None:
    """The LLM sometimes wraps the JSON in ```json ... ```. We strip the fences."""
    @dataclass
    class FencedLLM(FakeLLM):
        def chat(self, messages, **_kwargs) -> ChatResponse:
            self.calls.append(messages)
            return ChatResponse(
                content="```json\n" + json.dumps(self.canned) + "\n```",
                tool_calls=[], tokens_in=1, tokens_out=1,
                cost_usd=0.0, model="fake", finish_reason="stop",
            )

    llm = FencedLLM(canned={
        "goal": "A thing.",
        "tenancy_impact": "No cross-tenant impact.",
        "open_questions": "1. Confirm scope?",
    })
    spec = drafter.draft(
        llm=llm,
        issue_number=1,
        issue_title="X",
        issue_body="...",
        kind="design",
        today=_TODAY,
    )
    assert "A thing" in spec.markdown


@pytest.mark.parametrize(
    "title, expected_slug",
    [
        ("Maestro de Fuentes", "maestro-de-fuentes"),
        ("FIX: search broken!", "fix-search-broken"),
        ("   leading & trailing   ", "leading-trailing"),
        ("", "untitled"),
    ],
)
def test_slug_derivation(title: str, expected_slug: str) -> None:
    llm = FakeLLM(canned={
        "goal": "X.",
        "tenancy_impact": "No cross-tenant impact.",
        "open_questions": "1. ?",
    })
    spec = drafter.draft(
        llm=llm,
        issue_number=1,
        issue_title=title,
        issue_body="",
        kind="design",
        today=_TODAY,
    )
    assert spec.slug == expected_slug
