"""Support Triage agent core — STUB. Phase 10 of v7 roadmap.

Customer-facing agent. Lives inside Odoo + a Fly gateway.

See: docs/superpowers/specs/2026-05-16-support-triage-agent-design.md
"""

from __future__ import annotations

_DESIGN_SPEC = "docs/superpowers/specs/2026-05-16-support-triage-agent-design.md"


def run(runtime, payload: dict) -> None:
    runtime.logger.warn("support_triage.stub", spec=_DESIGN_SPEC, payload=payload)
