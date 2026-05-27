"""Contract tests for the bug-repro heuristic classifier."""

from __future__ import annotations

import pytest

from agents.spec_generator import bug_repro

REPRO_CONFIRMED = bug_repro.REPRO_CONFIRMED
NEEDS_REPRO_INFO = bug_repro.NEEDS_REPRO_INFO
NEEDS_FIXTURE = bug_repro.NEEDS_FIXTURE


def test_classify_repro_confirmed_with_steps_error_and_version() -> None:
    out = bug_repro.classify(
        title="Search broken with filter",
        body=(
            "Steps:\n"
            "1. Open Catalog\n"
            "2. Type 'foo'\n"
            "3. Apply filter Category=Bar\n\n"
            "Error: ValueError: empty filter\n"
            "Traceback (most recent call last):\n"
            "Odoo 19.0 on Chrome 125."
        ),
    )
    assert out.outcome == REPRO_CONFIRMED
    assert "has_numbered_or_bulleted_steps" in out.reasons
    assert "mentions_error_or_traceback" in out.reasons
    assert "mentions_version" in out.reasons


def test_classify_needs_repro_info_when_body_is_thin() -> None:
    out = bug_repro.classify(title="Doesn't work", body="The thing is broken.")
    assert out.outcome == NEEDS_REPRO_INFO
    assert "body_too_short" in out.reasons


def test_classify_needs_repro_info_when_no_steps_or_error() -> None:
    out = bug_repro.classify(
        title="Bug",
        body=(
            "I tried to use the product catalog this morning and noticed "
            "something was off. The screen looked different than usual and "
            "the buttons were in a weird spot. Not sure what's going on."
        ),
    )
    assert out.outcome == NEEDS_REPRO_INFO


def test_classify_needs_fixture_on_tenant_reference() -> None:
    out = bug_repro.classify(
        title="Wrong total on invoice",
        body=(
            "Steps:\n1. Open invoice #12345 for customer Acme.\n"
            "2. Look at totals — they're wrong.\nOdoo 19. Chrome."
        ),
    )
    assert out.outcome == NEEDS_FIXTURE
    assert any("fixture_hit" in reason for reason in out.reasons)


def test_classify_needs_fixture_on_production_url() -> None:
    out = bug_repro.classify(
        title="Bug",
        body=(
            "Steps:\n1. Go to https://example.goliatt.co/web#action=42\n"
            "2. Click save\n"
            "Error: 500 internal\nOdoo 19, Chrome."
        ),
    )
    assert out.outcome == NEEDS_FIXTURE


@pytest.mark.parametrize("outcome", [REPRO_CONFIRMED, NEEDS_REPRO_INFO, NEEDS_FIXTURE])
def test_comment_for_outcome_is_non_empty(outcome: str) -> None:
    msg = bug_repro.comment_for_outcome(outcome)
    assert msg and len(msg) > 20


def test_label_property() -> None:
    out = bug_repro.classify(title="x", body="y")
    assert out.label.startswith("repro:")
