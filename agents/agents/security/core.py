"""Security agent core — STUB. Phase 9 of v7 roadmap.

See: docs/superpowers/specs/2026-05-16-security-agent-design.md
"""

from __future__ import annotations

_DESIGN_SPEC = "docs/superpowers/specs/2026-05-16-security-agent-design.md"


def run(runtime, payload: dict) -> None:
    runtime.logger.warn("security.stub", spec=_DESIGN_SPEC, payload=payload)
