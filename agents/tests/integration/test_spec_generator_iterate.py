"""Integration test for spec_generator.core.iterate (PR2: reply-iteration).

Exercises §5.3 of the design spec: a reporter comment on the original issue
gets the spec refined and acknowledged; a `/confirm` reply applies the
intent-confirmed label and posts the close-out comment.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from agents.config import Bindings, Config, RuntimeConfig
from agents.ports import ChatResponse, Comment, Issue, PullRequest
from agents.spec_generator import core

# ---------------------------------------------------------------------------
# Fakes (mirror the PR1 integration test fakes — kept separate so the two
# files can evolve independently and each one prints a focused failure)
# ---------------------------------------------------------------------------

@dataclass
class FakeLLM:
    canned: dict[str, Any] = field(default_factory=dict)
    calls: list[Any] = field(default_factory=list)

    def chat(self, messages, *, model=None, max_tokens=4096,
             temperature=0.2, tools=None, stop_sequences=None) -> ChatResponse:
        self.calls.append(messages)
        return ChatResponse(
            content=json.dumps(self.canned),
            tool_calls=[], tokens_in=1, tokens_out=1,
            cost_usd=0.0, model="fake", finish_reason="stop",
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


@dataclass
class FakeRepo:
    files: dict[str, bytes] = field(default_factory=dict)
    checked_out: list[tuple[str, str]] = field(default_factory=list)
    written: dict[str, bytes] = field(default_factory=dict)
    commits: list[dict[str, Any]] = field(default_factory=list)
    pushed: list[str] = field(default_factory=list)
    prs: list[PullRequest] = field(default_factory=list)

    def checkout(self, branch, *, base="main"):
        self.checked_out.append((branch, base))

    def write(self, path, content):
        self.written[path] = content
        self.files[path] = content

    def commit(self, paths, message, *, author):
        sha = f"sha{len(self.commits) + 1}"
        self.commits.append({"paths": paths, "message": message, "author": author, "sha": sha})
        return sha

    def push(self, branch):
        self.pushed.append(branch)

    def open_pr(self, *, head, base, title, body, labels=()):
        raise NotImplementedError("not used in iterate tests")

    def add_labels(self, pr, labels):
        pass

    def remove_labels(self, pr, labels):
        pass

    def read(self, path, *, ref="HEAD"):
        return self.files.get(path, b"")

    def list_changed_files(self, base, head):
        return []

    def file_owners(self, path):
        return []


@dataclass
class FakeIssues:
    comments_posted: list[dict[str, Any]] = field(default_factory=list)
    labels_added: list[tuple[int, str]] = field(default_factory=list)
    labels_removed: list[tuple[int, str]] = field(default_factory=list)

    def open_issue(self, *, title, body, labels=()):
        raise NotImplementedError

    def comment(self, issue: Issue, body: str) -> Comment:
        self.comments_posted.append({"issue": issue.number, "body": body})
        return Comment(id=len(self.comments_posted), body=body,
                       author="spec-generator-bot", issue_number=issue.number)

    def edit_comment(self, comment, body):
        pass

    def add_label(self, issue: Issue, label: str):
        self.labels_added.append((issue.number, label))

    def remove_label(self, issue: Issue, label: str):
        self.labels_removed.append((issue.number, label))

    def list_issues(self, *, labels=None, state="open"):
        return []

    def search_similar(self, text, *, limit=5):
        return []


@dataclass
class FakeLogger:
    events: list[tuple[str, str, dict]] = field(default_factory=list)

    def _emit(self, level, msg, **f):
        self.events.append((level, msg, f))

    def info(self, msg, /, **f):
        self._emit("info", msg, **f)

    def warn(self, msg, /, **f):
        self._emit("warn", msg, **f)

    def error(self, msg, /, **f):
        self._emit("error", msg, **f)

    def debug(self, msg, /, **f):
        self._emit("debug", msg, **f)

    def bind(self, **_f):
        return self

    @contextmanager
    def span(self, name, /, **f):
        self._emit("info", f"{name}.start", **f)
        try:
            yield
        finally:
            self._emit("info", f"{name}.end", **f)


@dataclass
class FakeNotifier:
    sent: list[dict[str, Any]] = field(default_factory=list)

    def send(self, *, channel, summary, details=None, severity="info"):
        self.sent.append({"channel": channel, "summary": summary})


@dataclass
class FakeRuntime:
    llm: Any = None
    repo: Any = None
    issues: Any = None
    notifier: Any = None
    logger: Any = None
    config: Any = None


_SPEC_PATH = "docs/superpowers/specs/2026-05-27-maestro-de-fuentes-design.md"

_CURRENT_SPEC = """# Maestro de Fuentes — Design Spec

**Date:** 2026-05-27
**Author:** spec-generator-bot
**Status:** Draft
**Spec type:** design spec
**Linked issue:** #126

---

## 1. Goal

Add a Fund Master page.

## 2. Non-goals

- Does not change posting logic.

## 3. Tenancy impact

Per-tenant scoped; no cross-tenant data exposure.

## 4. Data model changes

Model goliatt.fund.master.

## 5. API surface

REST GET /goliatt/funds.

## 6. Security model

ir.model.access.

## 7. Test plan

Unit CRUD.

## 8. Rollout plan

Behind goliatt.fund_master flag.

## 9. Observability

Counter fund_master.create.

## 10. Open questions

1. Should fund codes be auto-generated?
"""


@pytest.fixture
def runtime() -> FakeRuntime:
    cfg = Config(
        runtime=RuntimeConfig(),
        bindings=Bindings(),
        extras={"github": {"org": "GoliattCo", "repo": "odoo-custom"}},
        agents={"spec_generator": {}},
    )
    repo = FakeRepo()
    repo.files[_SPEC_PATH] = _CURRENT_SPEC.encode("utf-8")
    return FakeRuntime(
        llm=FakeLLM(),
        repo=repo,
        issues=FakeIssues(),
        notifier=FakeNotifier(),
        logger=FakeLogger(),
        config=cfg,
    )


def _comment_payload(*, body: str, author: str = "reporter-1",
                     author_type: str = "User", issue_number: int = 126,
                     labels=("spec-drafted", "awaiting-reporter-confirm"),
                     spec_path: str = _SPEC_PATH, pr_number: int = 901,
                     ) -> dict[str, Any]:
    return {
        "action": "created",
        "issue": {
            "number": issue_number,
            "title": "Maestro de Fuentes",
            "labels": [{"name": label} for label in labels],
            "user": {"login": "reporter-1"},
            "html_url": f"https://github.example/org/repo/issues/{issue_number}",
        },
        "comment": {"body": body, "user": {"login": author, "type": author_type}},
        "repository": {"full_name": "GoliattCo/odoo-custom"},
        "spec_path": spec_path,
        "pr_number": pr_number,
    }


# ---------------------------------------------------------------------------
# Refinement path
# ---------------------------------------------------------------------------

def test_reporter_reply_refines_spec_and_acks(runtime: FakeRuntime) -> None:
    refined_markdown = _CURRENT_SPEC.replace(
        "Add a Fund Master page.",
        "Add a Fund Master page with auto-generated codes.",
    )
    runtime.llm = FakeLLM(canned={
        "markdown": refined_markdown,
        "summary": "Clarified that fund codes auto-generate.",
        "remaining_questions": ["Should the prefix be configurable?"],
        "confirmed": False,
    })

    core.iterate(runtime, _comment_payload(
        body="Yes — fund codes should auto-generate.",
    ))

    # Spec file rewritten on the spec branch.
    assert _SPEC_PATH in runtime.repo.written
    assert b"auto-generated codes" in runtime.repo.written[_SPEC_PATH]
    assert ("agent/spec-126", "main") in runtime.repo.checked_out
    assert "agent/spec-126" in runtime.repo.pushed

    # Commit message captures the LLM's one-liner summary.
    assert any("revise per reporter Q&A: Clarified" in c["message"]
               for c in runtime.repo.commits)

    # Acknowledgement comment posted with remaining-question count.
    assert len(runtime.issues.comments_posted) == 1
    body = runtime.issues.comments_posted[0]["body"]
    assert "Updated the spec" in body
    assert "1 open question" in body
    assert "configurable" in body


def test_bot_own_comment_is_ignored(runtime: FakeRuntime) -> None:
    core.iterate(runtime, _comment_payload(
        body="Anything else?",
        author="spec-generator-bot",
        author_type="Bot",
    ))
    assert runtime.repo.written == {}
    assert runtime.issues.comments_posted == []


def test_pr_not_in_awaiting_state_is_skipped(runtime: FakeRuntime) -> None:
    core.iterate(runtime, _comment_payload(
        body="More info",
        labels=("intent-confirmed",),
    ))
    assert runtime.repo.written == {}
    assert runtime.issues.comments_posted == []


def test_missing_spec_path_logs_warning(runtime: FakeRuntime) -> None:
    payload = _comment_payload(body="More info")
    payload["spec_path"] = ""
    core.iterate(runtime, payload)
    assert runtime.repo.written == {}
    assert any("no_spec_path" in e[1] for e in runtime.logger.events)


def test_shadow_mode_skips_write(runtime: FakeRuntime) -> None:
    runtime.config.agents["spec_generator"] = {"shadow_mode": True}
    runtime.llm = FakeLLM(canned={
        "markdown": _CURRENT_SPEC + "\n",
        "summary": "Noted.",
        "remaining_questions": [],
        "confirmed": False,
    })
    core.iterate(runtime, _comment_payload(body="More info"))
    assert runtime.repo.written == {}
    assert runtime.issues.comments_posted == []
    assert any("shadow_mode_skip_write" in e[1] for e in runtime.logger.events)


# ---------------------------------------------------------------------------
# /confirm path
# ---------------------------------------------------------------------------

def test_slash_confirm_applies_intent_confirmed_label(runtime: FakeRuntime) -> None:
    core.iterate(runtime, _comment_payload(body="Looks good. /confirm"))
    assert (901, "intent-confirmed") in runtime.issues.labels_added
    # The awaiting label is also cleaned up from the same target.
    assert (901, "awaiting-reporter-confirm") in runtime.issues.labels_removed
    # No LLM call should have happened — confirm short-circuits.
    assert runtime.llm.calls == []
    # Acknowledgement on the issue thread (not the PR) — for the Slack relay.
    assert any("Implementation Agent" in c["body"]
               for c in runtime.issues.comments_posted)
    assert runtime.issues.comments_posted[0]["issue"] == 126


def test_slash_confirm_is_idempotent_when_already_confirmed(
    runtime: FakeRuntime,
) -> None:
    core.iterate(runtime, _comment_payload(
        body="/confirm",
        labels=("spec-drafted", "intent-confirmed"),
    ))
    assert runtime.issues.labels_added == []
    assert any("already_confirmed" in e[1] for e in runtime.logger.events)


def test_slash_confirm_targets_issue_when_pr_number_missing(
    runtime: FakeRuntime,
) -> None:
    payload = _comment_payload(body="/confirm")
    payload["pr_number"] = 0
    core.iterate(runtime, payload)
    # Fall back to labelling the issue itself.
    assert (126, "intent-confirmed") in runtime.issues.labels_added


def test_confirm_in_shadow_mode_does_not_apply_label(runtime: FakeRuntime) -> None:
    runtime.config.agents["spec_generator"] = {"shadow_mode": True}
    core.iterate(runtime, _comment_payload(body="/confirm"))
    assert runtime.issues.labels_added == []
    assert any("shadow_mode_skip_confirm" in e[1] for e in runtime.logger.events)
