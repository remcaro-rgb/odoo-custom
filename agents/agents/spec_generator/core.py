"""Spec Generator core — turn issues into draft specs on agent/spec-NNN branches.

Implements §5.1 (feature-request initial draft) and §5.2 entry (bug intake;
the agentlab repro arm is deferred to a later PR — for now bug intakes are
drafted as fix-briefs marked "TBD — pending repro").

The reply-iteration (§5.3) and auto-confirm sweep (§5.4) handlers live in
separate PRs but their entry points are wired here as stubs so the CLI's
`agents iterate spec-generator` keeps returning a clean exit code.

Design spec: docs/superpowers/specs/2026-05-16-spec-generator-agent-design.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..ports import GitIdentity, PullRequest
from . import drafter, intake

_DESIGN_SPEC = "docs/superpowers/specs/2026-05-16-spec-generator-agent-design.md"

_DEFAULT_BOT_LOGIN = "spec-generator-bot"
_DEFAULT_BOT_EMAIL = "spec-generator-bot@goliatt.co"
_DEFAULT_NOTIFIER_CHANNEL = "#devops-intake"

_DRAFT_LABELS = ("spec-drafted", "awaiting-reporter-confirm")


def run(runtime, payload: dict[str, Any]) -> None:
    """Handle an `issues.opened|labeled` webhook payload.

    The runtime must provide: llm, repo, issues, logger. notifier is optional
    (we ping #devops-intake when present).
    """
    log = runtime.logger.bind(agent="spec_generator")
    ix = intake.parse(payload)
    log.info(
        "spec_generator.intake",
        issue=ix.issue_number,
        action=ix.action,
        classification=ix.classification,
        labels=list(ix.labels),
    )

    if ix.classification == "unrouted":
        log.debug("spec_generator.skip_unrouted", issue=ix.issue_number)
        return
    if ix.classification == "sensitive":
        log.warn("spec_generator.sensitive_topic", issue=ix.issue_number)
        _notify(runtime, _agent_cfg(runtime),
                f":warning: Issue #{ix.issue_number} ({ix.issue_url}) looks "
                "sensitive (billing / security / legal). Routing to support inbox.")
        return
    if ix.classification == "stale":
        log.info("spec_generator.stale_issue", issue=ix.issue_number)
        return

    if ix.issue_number == 0:
        log.warn("spec_generator.no_issue_in_payload")
        return

    # Idempotency: if a spec PR already exists for this issue, exit.
    branch = f"agent/spec-{ix.issue_number}"
    if _has_existing_spec_pr(runtime, branch):
        log.info("spec_generator.already_drafted", issue=ix.issue_number, branch=branch)
        return

    cfg = _agent_cfg(runtime)

    if runtime.llm is None or runtime.repo is None or runtime.issues is None:
        log.error("spec_generator.missing_ports",
                  llm=runtime.llm is not None,
                  repo=runtime.repo is not None,
                  issues=runtime.issues is not None,
                  reason="One or more required ports unbound — see config.bindings.")
        return

    with log.span("spec_generator.draft", issue=ix.issue_number, kind=ix.spec_kind):
        drafted = drafter.draft(
            llm=runtime.llm,
            issue_number=ix.issue_number,
            issue_title=ix.issue_title,
            issue_body=ix.issue_body,
            kind=ix.spec_kind,
            today=datetime.now(UTC),
        )

    if cfg.get("shadow_mode"):
        log.info("spec_generator.shadow_mode_skip_write",
                 issue=ix.issue_number, spec_path=drafted.file_path)
        return

    runtime.repo.checkout(branch, base="main")
    runtime.repo.write(drafted.file_path, drafted.markdown.encode("utf-8"))
    runtime.repo.commit(
        [drafted.file_path],
        f"[spec-generator] draft: {drafted.slug}",
        author=_bot_identity(cfg),
    )
    runtime.repo.push(branch)

    pr_title = f"[agent:spec-generator] spec: {drafted.slug}"
    pr_body = _pr_body(
        issue_number=ix.issue_number,
        issue_url=ix.issue_url,
        spec_path=drafted.file_path,
        open_questions=drafted.open_questions,
        kind=ix.spec_kind,
    )
    pr: PullRequest = runtime.repo.open_pr(
        head=branch,
        base="main",
        title=pr_title,
        body=pr_body,
        labels=_DRAFT_LABELS,
    )
    log.info("spec_generator.pr_opened",
             issue=ix.issue_number, pr=pr.number, branch=branch)

    # Comment on the original issue asking the reporter to confirm intent.
    from ..ports import Issue
    issue_handle = Issue(
        number=ix.issue_number,
        title=ix.issue_title,
        body="",
        labels=ix.labels,
        state="open",
        author=ix.issue_author,
        url=ix.issue_url,
    )
    runtime.issues.comment(issue_handle, _issue_comment_body(
        pr=pr, drafted_questions=drafted.open_questions,
    ))
    log.info("spec_generator.issue_commented", issue=ix.issue_number, pr=pr.number)

    _notify(runtime, cfg,
            f":memo: Spec drafted for #{ix.issue_number}: {pr.url}")


def iterate(runtime, payload: dict[str, Any]) -> None:
    """Reporter-iteration handler. Implemented in a follow-up PR.

    Kept as a clean no-op so `agents iterate spec-generator` exits zero and
    the iterate workflow's plumbing can be tested today.
    """
    runtime.logger.info(
        "spec_generator.iterate.pending", spec=_DESIGN_SPEC, payload=payload,
    )


def sweep(runtime, payload: dict[str, Any]) -> None:
    """Auto-confirm sweep handler. Implemented in a follow-up PR."""
    runtime.logger.info(
        "spec_generator.sweep.pending", spec=_DESIGN_SPEC, payload=payload,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_existing_spec_pr(runtime, branch: str) -> bool:
    """Best-effort check: does a PR on this branch already exist?

    The Repo port doesn't expose `list_prs`, so this is currently a soft
    signal — we ask the issues tracker for issues that look like our PR
    title. When run on a real GitHub adapter the open_pr() call below will
    fail with a 422 if the branch already has a PR, which is a safer hard
    backstop than this probe.
    """
    list_issues = getattr(runtime.issues, "list_issues", None)
    if list_issues is None:
        return False
    try:
        candidates = list_issues(labels=("spec-drafted",), state="open")
    except Exception:  # noqa: BLE001 — best-effort idempotency probe only
        return False
    return any(branch in (issue.body or "") for issue in candidates)


def _pr_body(
    *,
    issue_number: int,
    issue_url: str,
    spec_path: str,
    open_questions: tuple[str, ...],
    kind: str,
) -> str:
    questions_md = "\n".join(f"- {q}" for q in open_questions) or "- (none surfaced)"
    return (
        f"Drafted from issue #{issue_number} ({issue_url}).\n\n"
        f"Kind: {kind} spec\n"
        f"Spec: {spec_path}\n\n"
        f"## Open questions for the reporter\n\n"
        f"{questions_md}\n\n"
        f"This PR is `awaiting-reporter-confirm`. Comment `/confirm` on the "
        f"linked issue (or stay silent 24h) to flip the `intent-confirmed` "
        f"label and trigger the Implementation Agent.\n"
    )


def _issue_comment_body(
    *,
    pr: PullRequest,
    drafted_questions: tuple[str, ...],
) -> str:
    if drafted_questions:
        q_block = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(drafted_questions))
        ask = (
            f"Please confirm the intent and answer these "
            f"{len(drafted_questions)} question(s):\n\n{q_block}"
        )
    else:
        ask = "Please confirm the intent by commenting `/confirm`."
    return (
        f":memo: I drafted a spec for this issue at {pr.url}.\n\n"
        f"{ask}\n\n"
        f"_If you don't reply within 24h I'll auto-confirm and start "
        f"implementation. Comment `/reopen` within 7 days of that to halt._"
    )


def _notify(runtime, cfg: dict, summary: str) -> None:
    notifier = getattr(runtime, "notifier", None)
    if notifier is None:
        return
    channel = cfg.get("notifier_channel", _DEFAULT_NOTIFIER_CHANNEL)
    try:
        notifier.send(channel=channel, summary=summary)
    except Exception:  # noqa: BLE001 — notifier is best-effort
        runtime.logger.debug("spec_generator.notify_failed")


def _agent_cfg(runtime) -> dict:
    """Return the agents.spec_generator config block (or empty)."""
    return (runtime.config.agents or {}).get("spec_generator", {})


def _bot_identity(cfg: dict) -> GitIdentity:
    return GitIdentity(
        name=cfg.get("bot_login", _DEFAULT_BOT_LOGIN),
        email=cfg.get("bot_email", _DEFAULT_BOT_EMAIL),
    )
