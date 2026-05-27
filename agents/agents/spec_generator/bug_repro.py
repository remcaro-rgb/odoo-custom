"""Bug-repro heuristic — PR4 of the Spec Generator rollout.

Classifies an incoming bug intake into one of three outcomes BEFORE we
spend an LLM token on the fix-brief:

- ``repro-confirmed``  → enough information to draft a fix-brief.
- ``needs-repro-info`` → ambiguous report; the reporter must clarify before
                         we can responsibly draft.
- ``needs-fixture``    → reproducing requires customer-specific data; route
                         to security-lead for a sanitised agentlab fixture.

This is a pure heuristic over the issue title + body. The full agentlab
Playwright shim (see §5.2 of the design spec, "3a. If classification ==
'bug'") is tracked as a backlog item — when it lands, the classifier
output becomes the *fast path* and agentlab is only invoked when the
heuristic returns ``repro-confirmed``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REPRO_CONFIRMED = "repro-confirmed"
NEEDS_REPRO_INFO = "needs-repro-info"
NEEDS_FIXTURE = "needs-fixture"

# Patterns that strongly indicate the report references customer-specific
# state — the agent must not draft against this without a sanitised fixture.
_FIXTURE_PATTERNS = (
    r"(?i)\bcustomer\s+\w+\b",                   # "customer Acme"
    r"(?i)\btenant\s+\w+\b",                     # "tenant prod-123"
    r"(?i)\b(production|live|prod)\s+(data|database|tenant)\b",
    r"(?i)\baccount\s+number\s+[\w-]+",
    r"(?i)\binvoice\s+#?\d+",
    r"(?i)\bSO\d{3,}\b",                          # sales order references
    r"(?i)\bPO\d{3,}\b",                          # purchase order references
    r"(?i)https?://[\w.-]+\.goliatt\.co/",       # links into a live tenant
)

# Cues that the report DOES have repro information.
_STEPS_NEEDLE = re.compile(r"(?im)^\s*(\d+[.)]|[-*])\s")        # numbered/bulleted list
_ERROR_NEEDLE = re.compile(r"(?i)(traceback|error[:\-]\s|exception\b|stack[\s_-]?trace)")
_VERSION_NEEDLE = re.compile(r"(?i)(odoo\s*\d+|v\d+\.\d+|version[:\s]+\d)")
_BROWSER_NEEDLE = re.compile(r"(?i)(chrome|firefox|safari|edge|playwright)")


@dataclass(frozen=True)
class ReproClassification:
    outcome: str                    # one of the three constants above
    confidence: float               # 0.0 — 1.0
    reasons: tuple[str, ...]        # human-readable evidence

    @property
    def label(self) -> str:
        """Convenient mapping to the GitHub label name."""
        return f"repro:{self.outcome}"


def classify(*, title: str, body: str) -> ReproClassification:
    text = f"{title}\n{body}".strip()

    fixture_hits = [p for p in _FIXTURE_PATTERNS if re.search(p, text)]
    if fixture_hits:
        return ReproClassification(
            outcome=NEEDS_FIXTURE,
            confidence=min(1.0, 0.5 + 0.2 * len(fixture_hits)),
            reasons=tuple(f"fixture_hit:{p}" for p in fixture_hits[:3]),
        )

    score = 0
    reasons: list[str] = []
    if _STEPS_NEEDLE.search(body):
        score += 1
        reasons.append("has_numbered_or_bulleted_steps")
    if _ERROR_NEEDLE.search(body):
        score += 1
        reasons.append("mentions_error_or_traceback")
    if _VERSION_NEEDLE.search(body):
        score += 1
        reasons.append("mentions_version")
    if _BROWSER_NEEDLE.search(body):
        score += 1
        reasons.append("mentions_browser")
    if len(body.strip()) < 80:
        reasons.append("body_too_short")
        # short bodies are never confirmed even if they tick a box
        return ReproClassification(
            outcome=NEEDS_REPRO_INFO,
            confidence=0.7,
            reasons=tuple(reasons),
        )

    if score >= 2:
        return ReproClassification(
            outcome=REPRO_CONFIRMED,
            confidence=min(1.0, 0.5 + 0.15 * score),
            reasons=tuple(reasons),
        )
    return ReproClassification(
        outcome=NEEDS_REPRO_INFO,
        confidence=0.6,
        reasons=tuple(reasons) or ("no_repro_signal_detected",),
    )


def comment_for_outcome(outcome: str) -> str:
    """The follow-up sentence the issue comment uses for each outcome."""
    if outcome == REPRO_CONFIRMED:
        return ("Your report has enough detail for a fix-brief draft. "
                "Confirm the spec captures your intent.")
    if outcome == NEEDS_FIXTURE:
        return (":lock: This looks like it references production data. I'm "
                "routing this to security-lead so they can prepare a "
                "sanitised agentlab fixture before we draft a fix-brief.")
    return ("I couldn't see a clean repro in the report. Could you add: "
            "the exact steps (numbered), the error you saw (copy/paste any "
            "traceback), the Odoo version, and the browser?")
