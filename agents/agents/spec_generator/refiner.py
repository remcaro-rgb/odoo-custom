"""Refiner — integrate a reporter's reply into an existing spec.

The refiner is invoked when a non-bot user comments on a tracked
``agent/spec-<N>`` issue (or the spec PR itself) while the spec PR is in
``spec-drafted`` / ``awaiting-reporter-confirm`` state. It rewrites the
spec markdown to incorporate the reply, asks the LLM for a one-line
summary of *what changed*, and surfaces any remaining open questions.

The refiner does NOT decide whether intent is confirmed — that's the
caller's job (it looks for ``/confirm`` in the reply before invoking
the refiner).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..ports import LLMProvider, Message


@dataclass(frozen=True)
class RefinedSpec:
    markdown: str                       # updated full spec body
    change_summary: str                 # one-line summary of what changed
    remaining_questions: tuple[str, ...]
    confirmed_signal: bool              # True if the LLM saw a confirm signal


_SYSTEM_PROMPT = (
    "You are the Spec Generator agent refining an existing draft spec. The "
    "reporter just replied with a clarification, additional context, or a "
    "correction. Integrate their reply into the spec markdown WITHOUT "
    "restructuring it: keep the same headings and section order; only change "
    "the section bodies that the reply affects. Preserve all section "
    "headings exactly. Reply with a single JSON object: "
    '{"markdown": "...full updated spec...", "summary": "one-line what '
    'changed", "remaining_questions": ["question?", ...], "confirmed": false}.'
)


def refine(
    *,
    llm: LLMProvider,
    current_spec_md: str,
    reporter_reply: str,
    kind: str,                          # "design" | "fix"
) -> RefinedSpec:
    """Ask the LLM to rewrite the spec with the reply applied; return both."""
    prompt = (
        f"Spec kind: {kind}.\n\n"
        f"=== Current spec ===\n{current_spec_md}\n=== End ===\n\n"
        f"=== Reporter reply ===\n{reporter_reply}\n=== End ===\n\n"
        "Return the updated spec JSON object."
    )
    response = llm.chat(
        [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=prompt),
        ],
        max_tokens=6000,
        temperature=0.2,
    )
    payload = _extract_json(response.content)

    markdown = (payload.get("markdown") or "").strip() or current_spec_md
    summary = (payload.get("summary") or "").strip() or "spec revised"
    raw_qs = payload.get("remaining_questions") or []
    if isinstance(raw_qs, list):
        questions = tuple(str(q).strip() for q in raw_qs if str(q).strip())
    else:
        questions = ()
    confirmed = bool(payload.get("confirmed", False))

    # If the LLM dropped section headings, fall back to the original so we
    # never break spec-quality's structural checks downstream.
    if not _has_template_headings(markdown, kind=kind):
        markdown = current_spec_md

    return RefinedSpec(
        markdown=markdown if markdown.endswith("\n") else markdown + "\n",
        change_summary=summary[:200],
        remaining_questions=questions,
        confirmed_signal=confirmed,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
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
                    import json
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return {}
    return {}


def _has_template_headings(md: str, *, kind: str) -> bool:
    needles = {
        "design": ("## 1. Goal", "## 3. Tenancy impact", "## 10. Open questions"),
        "fix": ("## 1. Symptom", "## 2. Repro", "## 4. Root cause"),
    }[kind]
    return all(needle in md for needle in needles)
