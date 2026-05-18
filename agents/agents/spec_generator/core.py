"""Spec Generator core — STUB.

The full implementation lands in Phase 7 (weeks 11–12 of the v7 roadmap).
This stub makes `agents run spec-generator` not crash; it emits a clear
"not yet implemented" message and a pointer to the design spec.

When Phase 7 starts, replace this with the modules described in the design
spec: intake, classifier, repro, drafter, refiner, dup_detector, commenter.
"""

from __future__ import annotations


_DESIGN_SPEC = "docs/superpowers/specs/2026-05-16-spec-generator-agent-design.md"


def run(runtime, payload: dict) -> None:
    runtime.logger.warn(
        "spec_generator.stub",
        msg="Spec Generator not yet implemented. See design spec for the plan.",
        spec=_DESIGN_SPEC,
        payload=payload,
    )


def iterate(runtime, payload: dict) -> None:
    runtime.logger.warn("spec_generator.iterate.stub", spec=_DESIGN_SPEC, payload=payload)
