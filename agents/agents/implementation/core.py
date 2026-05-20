"""Implementation agent core — STUB.

The full implementation lands in Phase 8 (weeks 13–15 of the v7 roadmap).
This stub makes the CLI not crash; replace with the design-spec modules
(planner, coder, gate1, preview, classifier, commenter, state_machine).
"""

from __future__ import annotations

_DESIGN_SPEC = "docs/superpowers/specs/2026-05-16-implementation-agent-design.md"


def run(runtime, payload: dict) -> None:
    runtime.logger.warn(
        "implementation.stub",
        msg="Implementation Agent not yet implemented.",
        spec=_DESIGN_SPEC,
        payload=payload,
    )


def iterate(runtime, payload: dict) -> None:
    runtime.logger.warn("implementation.iterate.stub", spec=_DESIGN_SPEC, payload=payload)


def handle_commit(runtime, payload: dict) -> None:
    runtime.logger.warn(
        "implementation.handle_commit.stub",
        spec=_DESIGN_SPEC,
        payload=payload,
    )


def preview_destroy(runtime, payload: dict) -> None:
    runtime.logger.warn("implementation.preview_destroy.stub",
                        spec=_DESIGN_SPEC, payload=payload)


def preview_list(runtime, payload: dict) -> None:
    runtime.logger.warn("implementation.preview_list.stub",
                        spec=_DESIGN_SPEC, payload=payload)
