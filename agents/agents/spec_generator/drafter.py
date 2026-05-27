"""Drafter — turn a structured intake into a design spec or fix brief.

The drafter loads one of the two templates from `docs/superpowers/specs/`
and asks the LLM to fill it in from the issue body. The LLM is asked for
JSON because section-by-section markdown reflows poorly through a chat
turn; the drafter then renders the JSON into markdown deterministically.

This keeps two important properties:
- The template structure is owned by `_TEMPLATE-*.md` files in the repo, not
  by the LLM. The drafter passes the section list as the schema.
- The spec-quality check's invariants (Tenancy section non-empty, ≥1 open
  question for design specs) are enforced here BEFORE we write the file,
  not only in CI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..ports import LLMProvider, Message

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = REPO_ROOT / "docs" / "superpowers" / "specs"
DESIGN_TEMPLATE = TEMPLATE_DIR / "_TEMPLATE-design.md"
FIX_TEMPLATE = TEMPLATE_DIR / "_TEMPLATE-fix.md"

# Sections we ask the LLM to populate. Keys match the heading slugs in the
# templates; values are short prompts that surface in the LLM instructions.
DESIGN_SECTIONS: tuple[tuple[str, str], ...] = (
    ("goal", "One paragraph: the outcome and who benefits."),
    ("non_goals", "Bullets explicitly out of scope."),
    ("tenancy_impact",
     "MANDATORY non-empty. Does this touch tenant boundary, require per-tenant "
     "migration, change saas_tenant_gate? Could data leak across tenants?"),
    ("data_model", "New models, fields, indexes. Use Odoo ORM snippets if applicable."),
    ("api_surface", "New/changed controllers, RPC, JSON, webhooks."),
    ("security_model",
     "Record rules, ACLs, sensitive data exposure, one-paragraph "
     "tenancy-isolation argument."),
    ("test_plan", "Unit, integration, E2E (Playwright on agentlab), adversarial."),
    ("rollout_plan", "Feature-flagged? Which wave first? Migration cost? Rollback path?"),
    ("observability", "Logs, metrics, alerts."),
    ("open_questions", "MANDATORY: at least one numbered question for the reporter."),
)

FIX_SECTIONS: tuple[tuple[str, str], ...] = (
    ("symptom", "The user's report — quote relevant lines."),
    ("repro", "Numbered minimal repro steps on a fresh tenant."),
    ("affected_tenants", "Tenants impacted, severity, workaround availability."),
    ("root_cause", "The actual bug. Cite file:line if known, otherwise 'TBD — pending repro'."),
    ("proposed_fix", "Diff sketch. Pseudocode is fine."),
    ("regression_test", "The test that would have caught this. Pseudocode is fine."),
    ("rollout", "Hotfix or normal wave? Feature-flagged?"),
)


@dataclass(frozen=True)
class DraftedSpec:
    """A spec the drafter produced, ready to be written and committed."""

    kind: str                       # "design" | "fix"
    slug: str                       # e.g. "maestro-de-fuentes"
    file_path: str                  # repo-relative
    markdown: str                   # the full markdown body
    open_questions: tuple[str, ...]  # surfaced into the issue comment


def draft(
    *,
    llm: LLMProvider,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    kind: str,                       # "design" | "fix"
    today: datetime | None = None,
) -> DraftedSpec:
    """Ask the LLM to fill out the template, render markdown, validate, return."""
    today = today or datetime.now(UTC)
    slug = _slugify(issue_title)
    suffix = "design" if kind == "design" else "fix"
    file_name = f"{today.strftime('%Y-%m-%d')}-{slug}-{suffix}.md"
    file_path = f"docs/superpowers/specs/{file_name}"

    sections = DESIGN_SECTIONS if kind == "design" else FIX_SECTIONS
    schema = dict(sections)

    prompt = _build_prompt(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        kind=kind,
        schema=schema,
    )
    response = llm.chat(
        [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ],
        max_tokens=4096,
        temperature=0.2,
    )
    filled = _extract_json(response.content)

    # Enforce the spec-quality invariants here so the workflow gates don't
    # have to be the only line of defence.
    if kind == "design":
        if not _non_empty(filled.get("tenancy_impact")):
            filled["tenancy_impact"] = (
                "No impact identified from the issue body. The reporter "
                "should confirm: does this touch any per-tenant data, "
                "require a per-tenant migration, or change "
                "`saas_tenant_gate` configuration?"
            )
        if not _has_question(filled.get("open_questions", "")):
            existing = filled.get("open_questions", "").rstrip()
            filled["open_questions"] = (
                f"{existing}\n1. Can you confirm the intent of this request?"
            ).strip()

    markdown = _render(
        kind=kind,
        title=issue_title,
        issue_number=issue_number,
        today=today,
        filled=filled,
    )
    questions = _extract_questions(filled.get("open_questions", ""))
    return DraftedSpec(
        kind=kind,
        slug=slug,
        file_path=file_path,
        markdown=markdown,
        open_questions=questions,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are the Spec Generator agent. You convert a free-form GitHub issue "
    "into a structured spec section by section. Reply with a single JSON "
    "object whose keys match the requested section names and whose values "
    "are the markdown content of that section (no headings — the renderer "
    "adds them). Be concrete and short. If the issue body lacks the info "
    "for a section, write what is known and add a numbered open question."
)


def _build_prompt(
    *,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    kind: str,
    schema: dict[str, str],
) -> str:
    schema_lines = [f"  - {name}: {hint}" for name, hint in schema.items()]
    return (
        f"Issue #{issue_number} — kind={kind}\n"
        f"Title: {issue_title}\n\n"
        f"Body:\n{issue_body}\n\n"
        "Fill out these sections as JSON keys (no markdown headings inside):\n"
        + "\n".join(schema_lines)
        + "\n\nReturn ONLY the JSON object."
    )


def _extract_json(text: str) -> dict[str, str]:
    """Pull a JSON object out of the LLM response, tolerating code-fences."""
    # Strip code fences if present.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # Find the first balanced { ... } block.
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return {}
    return {}


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and len(value.strip()) >= 16


def _has_question(value: str) -> bool:
    return "?" in (value or "")


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    return (slug or "untitled")[:60]


def _extract_questions(open_questions_md: str) -> tuple[str, ...]:
    """Pull numbered questions out of the open_questions section body."""
    out: list[str] = []
    for line in (open_questions_md or "").splitlines():
        m = re.match(r"\s*\d+[.)]\s+(.*\?)\s*$", line)
        if m:
            out.append(m.group(1).strip())
    return tuple(out)


def _render(
    *,
    kind: str,
    title: str,
    issue_number: int,
    today: datetime,
    filled: dict[str, str],
) -> str:
    """Render the filled sections into the template's markdown shape."""
    date = today.strftime("%Y-%m-%d")
    if kind == "design":
        sections = DESIGN_SECTIONS
        heading_order = [
            ("1. Goal", "goal"),
            ("2. Non-goals", "non_goals"),
            ("3. Tenancy impact", "tenancy_impact"),
            ("4. Data model changes", "data_model"),
            ("5. API surface", "api_surface"),
            ("6. Security model", "security_model"),
            ("7. Test plan", "test_plan"),
            ("8. Rollout plan", "rollout_plan"),
            ("9. Observability", "observability"),
            ("10. Open questions", "open_questions"),
        ]
        header = (
            f"# {title} — Design Spec\n\n"
            f"**Date:** {date}\n"
            f"**Author:** spec-generator-bot (drafted from issue #{issue_number})\n"
            f"**Status:** Draft\n"
            f"**Spec type:** design spec\n"
            f"**Linked issue:** #{issue_number}\n\n"
            f"---\n\n"
        )
    else:
        sections = FIX_SECTIONS
        heading_order = [
            ("1. Symptom", "symptom"),
            ("2. Repro", "repro"),
            ("3. Affected tenants & severity", "affected_tenants"),
            ("4. Root cause", "root_cause"),
            ("5. Proposed fix", "proposed_fix"),
            ("6. Regression test", "regression_test"),
            ("7. Rollout", "rollout"),
        ]
        header = (
            f"# {title} — Fix Brief\n\n"
            f"**Date:** {date}\n"
            f"**Author:** spec-generator-bot (drafted from issue #{issue_number})\n"
            f"**Status:** Draft\n"
            f"**Spec type:** fix-brief\n"
            f"**Linked issue:** #{issue_number}\n\n"
            f"---\n\n"
        )

    known = {name for name, _ in sections}
    parts = [header]
    for heading, key in heading_order:
        body = (filled.get(key) or "_To be filled — see open questions._").strip()
        parts.append(f"## {heading}\n\n{body}\n")
    # Surface any unknown keys at the end so nothing the LLM produced is silently lost.
    extras = {k: v for k, v in filled.items() if k not in known}
    if extras:
        parts.append("## Notes from drafter\n")
        for k, v in extras.items():
            parts.append(f"**{k}:** {v}\n")
    return "\n".join(parts).rstrip() + "\n"
