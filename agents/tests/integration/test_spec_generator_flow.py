"""Integration test for the spec_generator agent core (PR1: intake + drafter)."""

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
# Fakes
# ---------------------------------------------------------------------------

@dataclass
class FakeLLM:
    canned: dict[str, str] = field(default_factory=dict)

    def chat(self, messages, *, model=None, max_tokens=4096,
             temperature=0.2, tools=None, stop_sequences=None) -> ChatResponse:
        return ChatResponse(
            content=json.dumps(self.canned),
            tool_calls=[],
            tokens_in=1, tokens_out=1,
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
    checked_out: list[tuple[str, str]] = field(default_factory=list)
    written: dict[str, bytes] = field(default_factory=dict)
    commits: list[dict[str, Any]] = field(default_factory=list)
    pushed: list[str] = field(default_factory=list)
    prs: list[PullRequest] = field(default_factory=list)

    def checkout(self, branch, *, base="main"):
        self.checked_out.append((branch, base))

    def write(self, path, content):
        self.written[path] = content

    def commit(self, paths, message, *, author):
        sha = f"sha{len(self.commits) + 1}"
        self.commits.append({"paths": paths, "message": message,
                             "author": author, "sha": sha})
        return sha

    def push(self, branch):
        self.pushed.append(branch)

    def open_pr(self, *, head, base, title, body, labels=()):
        pr = PullRequest(
            number=900 + len(self.prs) + 1,
            head_sha="abc1234",
            head_branch=head,
            base_branch=base,
            title=title,
            body=body,
            labels=labels,
            url=f"https://github.example/org/repo/pull/{900 + len(self.prs) + 1}",
        )
        self.prs.append(pr)
        return pr

    def add_labels(self, pr, labels):
        pass

    def remove_labels(self, pr, labels):
        pass

    def read(self, path, *, ref="HEAD"):
        return self.written.get(path, b"")

    def list_changed_files(self, base, head):
        return list(self.written.keys())

    def file_owners(self, path):
        return []


@dataclass
class FakeIssues:
    comments_posted: list[dict[str, Any]] = field(default_factory=list)
    labelled: list[tuple[int, str]] = field(default_factory=list)
    existing_open_issues: list[Issue] = field(default_factory=list)

    def open_issue(self, *, title, body, labels=()):
        raise NotImplementedError

    def comment(self, issue: Issue, body: str) -> Comment:
        self.comments_posted.append({"issue": issue.number, "body": body})
        return Comment(id=len(self.comments_posted), body=body,
                       author="spec-generator-bot", issue_number=issue.number)

    def edit_comment(self, comment, body):
        pass

    def add_label(self, issue, label):
        self.labelled.append((issue.number, label))

    def remove_label(self, issue, label):
        pass

    def list_issues(self, *, labels=None, state="open"):
        return list(self.existing_open_issues)

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
        self.sent.append({"channel": channel, "summary": summary,
                          "severity": severity})


@dataclass
class FakeRuntime:
    llm: Any = None
    repo: Any = None
    issues: Any = None
    notifier: Any = None
    logger: Any = None
    config: Any = None


@pytest.fixture
def runtime() -> FakeRuntime:
    cfg = Config(
        runtime=RuntimeConfig(),
        bindings=Bindings(),
        extras={"github": {"org": "GoliattCo", "repo": "odoo-custom"}},
        agents={"spec_generator": {}},
    )
    return FakeRuntime(
        llm=FakeLLM(canned=_canned_design()),
        repo=FakeRepo(),
        issues=FakeIssues(),
        notifier=FakeNotifier(),
        logger=FakeLogger(),
        config=cfg,
    )


def _canned_design() -> dict[str, str]:
    return {
        "goal": "Add a Fund Master page in Goliatt Contabilidad.",
        "non_goals": "- Does not change posting logic.",
        "tenancy_impact": "Per-tenant scoped; no cross-tenant data exposure.",
        "data_model": "Model goliatt.fund.master with name/code/balance.",
        "api_surface": "REST GET /goliatt/funds.",
        "security_model": "Standard ir.model.access with company_id scoping.",
        "test_plan": "Unit CRUD + integration tour.",
        "rollout_plan": "Behind goliatt.fund_master flag.",
        "observability": "Counter fund_master.create.",
        "open_questions": "1. Should fund codes be auto-generated?",
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def _payload_for_issue(*, number: int, title: str, body: str, labels: list[str],
                      action: str = "opened") -> dict[str, Any]:
    return {
        "action": action,
        "issue": {
            "number": number,
            "title": title,
            "body": body,
            "labels": [{"name": label} for label in labels],
            "user": {"login": "reporter-1"},
            "html_url": f"https://github.example/org/repo/issues/{number}",
        },
        "repository": {"full_name": "GoliattCo/odoo-custom"},
    }


def test_feature_request_opens_pr_and_comments_issue(runtime: FakeRuntime) -> None:
    payload = _payload_for_issue(
        number=126,
        title="Maestro de Fuentes",
        body="We need a Fund Master page in Contabilidad.",
        labels=["feature-request", "source:slack"],
    )

    core.run(runtime, payload)

    # 1. The feature branch was checked out from main.
    assert ("agent/spec-126", "main") in runtime.repo.checked_out

    # 2. A spec file was written under docs/superpowers/specs/ with a -design suffix.
    spec_paths = [p for p in runtime.repo.written if p.startswith("docs/superpowers/specs/")]
    assert spec_paths, runtime.repo.written
    assert spec_paths[0].endswith("-design.md")
    # And its body carries the canned LLM content.
    assert b"Maestro de Fuentes" in runtime.repo.written[spec_paths[0]]
    assert b"Fund Master" in runtime.repo.written[spec_paths[0]]

    # 3. A commit + push happened on the spec branch.
    assert any("[spec-generator] draft" in c["message"] for c in runtime.repo.commits)
    assert "agent/spec-126" in runtime.repo.pushed

    # 4. The PR was opened with the draft labels and its body contains the spec link.
    assert len(runtime.repo.prs) == 1
    pr = runtime.repo.prs[0]
    assert set(pr.labels) == {"spec-drafted", "awaiting-reporter-confirm"}
    assert "Spec: docs/superpowers/specs/" in pr.body  # spec-required gate
    assert "Open questions" in pr.body

    # 5. We commented on the original issue with the PR URL + the question.
    assert len(runtime.issues.comments_posted) == 1
    comment = runtime.issues.comments_posted[0]
    assert comment["issue"] == 126
    assert pr.url in comment["body"]
    assert "auto-generated" in comment["body"]  # the canned question surfaced

    # 6. The notifier received an intake ping.
    assert runtime.notifier.sent
    assert "#126" in runtime.notifier.sent[0]["summary"]


def test_bug_request_carries_repro_label_and_evidence(runtime: FakeRuntime) -> None:
    """PR4 acceptance: bug intakes get a repro:<outcome> label on the PR
    plus a follow-up sentence on the issue comment that matches the
    classifier's verdict."""
    runtime.llm = FakeLLM(canned={
        "symptom": "Filter breaks search.",
        "repro": "1. Open Catalog.\n2. Apply filter.",
        "affected_tenants": "All; severity medium.",
        "root_cause": "TBD",
        "proposed_fix": "Replace == with is None.",
        "regression_test": "Test empty filter.",
        "rollout": "Hotfix.",
    })
    payload = _payload_for_issue(
        number=140, title="Search broken with filter",
        body=(
            "Steps:\n1. Open Catalog\n2. Type 'foo'\n3. Apply filter X=Y\n"
            "Error: ValueError, traceback below.\nOdoo 19, Chrome."
        ),
        labels=["bug"],
    )
    core.run(runtime, payload)
    pr = runtime.repo.prs[0]
    assert "repro:repro-confirmed" in pr.labels
    # And the issue comment carries the matching follow-up.
    assert any("enough detail" in c["body"]
               for c in runtime.issues.comments_posted)


def test_bug_request_with_tenant_reference_gets_needs_fixture_label(
    runtime: FakeRuntime,
) -> None:
    runtime.llm = FakeLLM(canned={
        "symptom": "Wrong totals.",
        "repro": "1. Open invoice.\n2. Check totals.",
        "affected_tenants": "Specific.",
        "root_cause": "TBD",
        "proposed_fix": "TBD",
        "regression_test": "TBD",
        "rollout": "Hotfix.",
    })
    payload = _payload_for_issue(
        number=141, title="Wrong total on the sales order",
        body=(
            "Steps:\n1. Open SO12345 for customer Acme.\n"
            "2. Look at totals — wrong.\nOdoo 19, Chrome."
        ),
        labels=["bug"],
    )
    core.run(runtime, payload)
    pr = runtime.repo.prs[0]
    assert "repro:needs-fixture" in pr.labels
    assert any("sanitised agentlab fixture" in c["body"]
               for c in runtime.issues.comments_posted)


def test_bug_request_drafts_a_fix_brief(runtime: FakeRuntime) -> None:
    runtime.llm = FakeLLM(canned={
        "symptom": "Search returns no results when filter is set.",
        "repro": "1. Open Catalog.\n2. Apply filter Category=Bar.",
        "affected_tenants": "All tenants; severity medium.",
        "root_cause": "TBD — pending repro on agentlab.",
        "proposed_fix": "Replace == with is None.",
        "regression_test": "Test for empty-string filter resolves to None.",
        "rollout": "Hotfix flow.",
    })
    payload = _payload_for_issue(
        number=127, title="Search broken with filter",
        body="Filter on category breaks search.", labels=["bug"],
    )
    core.run(runtime, payload)
    written = list(runtime.repo.written.keys())
    assert written and written[0].endswith("-fix.md")
    assert b"Fix Brief" in runtime.repo.written[written[0]]


def test_unrouted_issue_is_skipped(runtime: FakeRuntime) -> None:
    payload = _payload_for_issue(
        number=128, title="Some doc tweak", body="Nothing labelled.",
        labels=["documentation"],
    )
    core.run(runtime, payload)
    assert runtime.repo.prs == []
    assert runtime.repo.written == {}
    assert runtime.issues.comments_posted == []


def test_sensitive_topic_is_skipped(runtime: FakeRuntime) -> None:
    payload = _payload_for_issue(
        number=129, title="Refund request",
        body="I want a refund and my chargeback processed.",
        labels=["feature-request"],
    )
    core.run(runtime, payload)
    assert runtime.repo.prs == []
    assert runtime.repo.written == {}
    # We DO notify so a human picks it up.
    assert any("sensitive" in m["summary"].lower() for m in runtime.notifier.sent)


def test_labeled_action_only_when_relevant_label_present(runtime: FakeRuntime) -> None:
    """An `issues.labeled` event for the routing label still drafts."""
    payload = _payload_for_issue(
        number=130, title="New feature",
        body="Add an export.", labels=["feature-request"],
        action="labeled",
    )
    payload["label"] = {"name": "feature-request"}
    core.run(runtime, payload)
    assert len(runtime.repo.prs) == 1


def test_missing_ports_logs_error_and_returns(runtime: FakeRuntime) -> None:
    runtime.llm = None
    payload = _payload_for_issue(
        number=131, title="X", body="y", labels=["feature-request"],
    )
    core.run(runtime, payload)
    assert runtime.repo.prs == []
    errors = [e for e in runtime.logger.events if e[0] == "error"]
    assert any("missing_ports" in e[1] for e in errors)


def test_shadow_mode_drafts_but_does_not_push_or_open_pr(runtime: FakeRuntime) -> None:
    """PR1 rollout: with shadow_mode=true the agent runs the drafter but
    skips checkout, commit, push, open_pr, and the issue comment. Logs an
    explicit ``shadow_mode_skip_write`` event so the dashboard can confirm
    the gate fired."""
    runtime.config.agents["spec_generator"] = {"shadow_mode": True}
    payload = _payload_for_issue(
        number=133, title="Shadowed feature", body="...",
        labels=["feature-request"],
    )
    core.run(runtime, payload)
    assert runtime.repo.prs == []
    assert runtime.repo.written == {}
    assert runtime.repo.pushed == []
    assert runtime.issues.comments_posted == []
    assert any("shadow_mode_skip_write" in e[1] for e in runtime.logger.events)


def test_already_drafted_issue_is_idempotent(runtime: FakeRuntime) -> None:
    """If list_issues returns one whose body mentions our branch, skip."""
    runtime.issues.existing_open_issues = [
        Issue(number=999, title="prior", body="agent/spec-132 is in flight",
              labels=("spec-drafted",), state="open", author="bot", url="..."),
    ]
    payload = _payload_for_issue(
        number=132, title="Already drafted", body="...",
        labels=["feature-request"],
    )
    core.run(runtime, payload)
    assert runtime.repo.prs == []
