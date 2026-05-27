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

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from ..ports import GitIdentity, Issue, PullRequest
from . import bug_repro, drafter, intake, refiner

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

    # For bug intakes, classify the repro state BEFORE we draft. Drives both
    # the PR label set and the follow-up sentence on the issue comment.
    repro: bug_repro.ReproClassification | None = None
    if ix.classification == "bug":
        repro = bug_repro.classify(title=ix.issue_title, body=ix.issue_body)
        log.info("spec_generator.bug_repro",
                 issue=ix.issue_number,
                 outcome=repro.outcome,
                 confidence=repro.confidence,
                 reasons=list(repro.reasons))

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
        repro=repro,
    )
    pr_labels = _DRAFT_LABELS + ((repro.label,) if repro else ())
    pr: PullRequest = runtime.repo.open_pr(
        head=branch,
        base="main",
        title=pr_title,
        body=pr_body,
        labels=pr_labels,
    )
    log.info("spec_generator.pr_opened",
             issue=ix.issue_number, pr=pr.number, branch=branch)

    # Comment on the original issue asking the reporter to confirm intent.
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
        pr=pr, drafted_questions=drafted.open_questions, repro=repro,
    ))
    log.info("spec_generator.issue_commented", issue=ix.issue_number, pr=pr.number)

    _notify(runtime, cfg,
            f":memo: Spec drafted for #{ix.issue_number}: {pr.url}")


_AWAITING_LABELS = frozenset(
    {"spec-drafted", "awaiting-reporter-confirm", "awaiting-reporter-reconfirm"}
)
_CONFIRM_PATTERN = r"(?:^|\s)/confirm\b"


def iterate(runtime, payload: dict[str, Any]) -> None:
    """Handle a reporter reply on a tracked spec issue (§5.3 of the design spec).

    Payload shape — accepts a raw ``issue_comment.created`` webhook event
    enriched by the workflow with ``spec_path`` and ``pr_number`` (the
    workflow's already running ``gh pr list --head agent/spec-N`` so it
    cheaply resolves both):

    .. code-block:: json

        {
          "action": "created",
          "issue": {"number": 126, "labels": [{"name": "..."}], ...},
          "comment": {"body": "...", "user": {"login": "...", "type": "User"}},
          "spec_path": "docs/superpowers/specs/<file>.md",
          "pr_number": 901,
          "repository": {"full_name": "GoliattCo/odoo-custom"}
        }
    """
    log = runtime.logger.bind(agent="spec_generator", path="iterate")
    issue_payload = payload.get("issue") or {}
    comment = payload.get("comment") or {}

    issue_number = int(issue_payload.get("number") or payload.get("issue_number") or 0)
    pr_number = int(payload.get("pr_number") or 0)
    spec_path = payload.get("spec_path") or ""
    if issue_number == 0:
        log.warn("spec_generator.iterate.no_issue")
        return

    labels = _payload_labels(issue_payload)
    if not (labels & _AWAITING_LABELS):
        log.debug("spec_generator.iterate.not_awaiting", issue=issue_number,
                  labels=list(labels))
        return

    cfg = _agent_cfg(runtime)
    bot_login = cfg.get("bot_login", _DEFAULT_BOT_LOGIN)
    user = comment.get("user") or {}
    author = user.get("login", "")
    if author == bot_login or user.get("type") == "Bot":
        log.debug("spec_generator.iterate.ignored_bot", author=author)
        return

    reply_body = (comment.get("body") or "").strip()
    if not reply_body:
        return

    # `/confirm` short-circuits — apply intent-confirmed label and exit.
    if re.search(_CONFIRM_PATTERN, reply_body, re.IGNORECASE):
        _mark_intent_confirmed(runtime, log, issue_number=issue_number,
                                pr_number=pr_number, labels=tuple(labels))
        return

    if runtime.llm is None or runtime.repo is None or runtime.issues is None:
        log.error("spec_generator.iterate.missing_ports",
                  llm=runtime.llm is not None,
                  repo=runtime.repo is not None,
                  issues=runtime.issues is not None)
        return

    if not spec_path:
        log.warn("spec_generator.iterate.no_spec_path", issue=issue_number,
                 hint="workflow must resolve spec_path from PR body via "
                      "grep -Eo 'docs/superpowers/specs/...md'")
        return

    branch = f"agent/spec-{issue_number}"
    runtime.repo.checkout(branch, base="main")
    current_md = runtime.repo.read(spec_path, ref="HEAD").decode("utf-8")
    kind = "fix" if spec_path.endswith("-fix.md") else "design"

    with log.span("spec_generator.refine", issue=issue_number, kind=kind):
        refined = refiner.refine(
            llm=runtime.llm,
            current_spec_md=current_md,
            reporter_reply=reply_body,
            kind=kind,
        )

    if cfg.get("shadow_mode"):
        log.info("spec_generator.iterate.shadow_mode_skip_write",
                 issue=issue_number, summary=refined.change_summary)
        return

    if refined.markdown != current_md:
        runtime.repo.write(spec_path, refined.markdown.encode("utf-8"))
        runtime.repo.commit(
            [spec_path],
            f"[spec-generator] revise per reporter Q&A: {refined.change_summary}",
            author=_bot_identity(cfg),
        )
        runtime.repo.push(branch)

    issue_handle = _issue_handle(issue_payload, issue_number=issue_number,
                                  labels=tuple(labels))
    runtime.issues.comment(issue_handle, _refinement_ack_body(refined))
    log.info("spec_generator.iterate.refined",
             issue=issue_number, summary=refined.change_summary,
             remaining=len(refined.remaining_questions))


def _mark_intent_confirmed(
    runtime, log, *, issue_number: int, pr_number: int, labels: tuple[str, ...],
) -> None:
    """Apply the ``intent-confirmed`` label and post the acknowledgement."""
    if "intent-confirmed" in labels:
        log.info("spec_generator.iterate.already_confirmed", issue=issue_number)
        return

    cfg = _agent_cfg(runtime)
    if cfg.get("shadow_mode"):
        log.info("spec_generator.iterate.shadow_mode_skip_confirm",
                 issue=issue_number, pr=pr_number)
        return

    if runtime.issues is None:
        log.error("spec_generator.iterate.no_issues_port")
        return

    # The intent-confirmed label lives on the PR (GitHub treats PRs as issues
    # for labels). The workflow passes pr_number; fall back to labelling the
    # original issue if pr_number is missing.
    label_target_n = pr_number or issue_number
    target = Issue(
        number=label_target_n, title="", body="", labels=labels,
        state="open", author="", url="",
    )
    runtime.issues.add_label(target, "intent-confirmed")
    # Also drop the awaiting-* labels so dashboards don't double-count.
    for stale in ("awaiting-reporter-confirm", "awaiting-reporter-reconfirm"):
        if stale in labels:
            try:
                runtime.issues.remove_label(target, stale)
            except Exception as exc:  # noqa: BLE001 — label removal is best-effort
                log.debug("spec_generator.iterate.remove_label_failed",
                          label=stale, error=str(exc))

    # Acknowledge on the issue thread so the reporter (and the Slack relay)
    # can see the state change.
    ack_target = Issue(
        number=issue_number, title="", body="", labels=labels,
        state="open", author="", url="",
    )
    runtime.issues.comment(ack_target, (
        ":white_check_mark: Intent confirmed. The Implementation Agent will "
        "pick up from here. Comment `/reopen` within 7 days to halt."
    ))
    log.info("spec_generator.iterate.confirmed",
             issue=issue_number, pr=pr_number)


_AUTO_CONFIRM_AFTER = timedelta(hours=24)
_NEEDS_CLARIFICATION_MARKER = "[NEEDS CLARIFICATION]"


def sweep(runtime, payload: dict[str, Any]) -> dict[str, Any]:
    """Walk the candidate PR list and auto-confirm those past the 24h window.

    Payload contract (resolved by the spec-generator-sweep workflow via
    ``gh pr list --json number,headRefName,labels,updatedAt,body``):

    .. code-block:: json

        {
          "now": "2026-05-27T09:00:00+00:00",   // optional; defaults to UTC now
          "dry_run": false,
          "candidates": [
            {
              "pr_number": 901,
              "issue_number": 126,
              "branch": "agent/spec-126",
              "spec_path": "docs/superpowers/specs/...md",
              "updated_at": "2026-05-25T08:30:00+00:00",
              "labels": ["spec-drafted", "awaiting-reporter-confirm"]
            }
          ]
        }

    Returns a summary ``{"decisions": [...], "confirmed": [...]}`` so the
    workflow can pipe it to Axiom for the dashboard.
    """
    log = runtime.logger.bind(agent="spec_generator", path="sweep")
    candidates = payload.get("candidates") or []
    now = _parse_iso(payload.get("now")) or datetime.now(UTC)
    dry_run = bool(payload.get("dry_run", False))
    cfg = _agent_cfg(runtime)
    act = not (dry_run or cfg.get("shadow_mode"))

    decisions: list[dict[str, Any]] = []
    confirmed: list[int] = []

    for cand in candidates:
        decision = _decide_sweep(cand, now=now)
        decisions.append(decision)
        if decision["action"] != "confirm":
            log.debug("spec_generator.sweep.skip",
                      pr=decision["pr"], reason=decision["reason"])
            continue
        if not act:
            log.info("spec_generator.sweep.dry_run",
                     pr=decision["pr"], reason=decision["reason"])
            continue
        if runtime.issues is None:
            log.error("spec_generator.sweep.no_issues_port")
            continue
        target = Issue(
            number=int(cand.get("pr_number") or cand.get("issue_number") or 0),
            title="", body="", labels=tuple(cand.get("labels", [])),
            state="open", author="", url="",
        )
        runtime.issues.add_label(target, "intent-confirmed")
        for stale in ("awaiting-reporter-confirm", "awaiting-reporter-reconfirm"):
            if stale in cand.get("labels", []):
                try:
                    runtime.issues.remove_label(target, stale)
                except Exception as exc:  # noqa: BLE001
                    log.debug("spec_generator.sweep.remove_label_failed",
                              error=str(exc))
        issue_target = Issue(
            number=int(cand.get("issue_number") or 0), title="", body="",
            labels=(), state="open", author="", url="",
        )
        if issue_target.number:
            runtime.issues.comment(issue_target, (
                ":hourglass_flowing_sand: No further input received within "
                "24h; treating the spec as confirmed. Comment `/reopen` "
                "within 7 days to halt implementation."
            ))
        confirmed.append(target.number)
        log.info("spec_generator.sweep.confirmed",
                 pr=target.number, issue=issue_target.number)

    summary = {"decisions": decisions, "confirmed": confirmed,
               "act": act, "total": len(decisions)}
    log.info("spec_generator.sweep.summary", **{k: summary[k]
             for k in ("confirmed", "act", "total")})
    return summary


def _decide_sweep(cand: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    pr_number = int(cand.get("pr_number") or 0)
    branch = str(cand.get("branch") or "")
    spec_path = str(cand.get("spec_path") or "")
    labels = list(cand.get("labels", []))
    updated_at = _parse_iso(cand.get("updated_at"))

    if "intent-confirmed" in labels:
        return _decision(pr_number, branch, spec_path, "skip", "already_confirmed")
    if updated_at is None:
        return _decision(pr_number, branch, spec_path, "skip", "no_updated_at")
    age = now - updated_at
    if age < _AUTO_CONFIRM_AFTER:
        return _decision(pr_number, branch, spec_path, "skip",
                         f"too_young:{int(age.total_seconds())}s")
    body = cand.get("spec_body") or ""
    if _NEEDS_CLARIFICATION_MARKER in body:
        return _decision(pr_number, branch, spec_path, "skip",
                         "needs_clarification_marker")
    return _decision(pr_number, branch, spec_path, "confirm",
                     f"silent_for:{int(age.total_seconds() / 3600)}h")


def _decision(
    pr: int, branch: str, spec_path: str, action: str, reason: str,
) -> dict[str, Any]:
    return {"pr": pr, "branch": branch, "spec_path": spec_path,
            "action": action, "reason": reason}


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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
    repro: bug_repro.ReproClassification | None = None,
) -> str:
    questions_md = "\n".join(f"- {q}" for q in open_questions) or "- (none surfaced)"
    repro_block = ""
    if repro is not None:
        evidence = ", ".join(repro.reasons) or "none"
        repro_block = (
            f"\n## Bug repro classifier\n\n"
            f"Outcome: `{repro.outcome}` (confidence {repro.confidence:.2f})\n"
            f"Evidence: {evidence}\n"
        )
    return (
        f"Drafted from issue #{issue_number} ({issue_url}).\n\n"
        f"Kind: {kind} spec\n"
        f"Spec: {spec_path}\n\n"
        f"## Open questions for the reporter\n\n"
        f"{questions_md}\n"
        f"{repro_block}\n"
        f"This PR is `awaiting-reporter-confirm`. Comment `/confirm` on the "
        f"linked issue (or stay silent 24h) to flip the `intent-confirmed` "
        f"label and trigger the Implementation Agent.\n"
    )


def _issue_comment_body(
    *,
    pr: PullRequest,
    drafted_questions: tuple[str, ...],
    repro: bug_repro.ReproClassification | None = None,
) -> str:
    if drafted_questions:
        q_block = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(drafted_questions))
        ask = (
            f"Please confirm the intent and answer these "
            f"{len(drafted_questions)} question(s):\n\n{q_block}"
        )
    else:
        ask = "Please confirm the intent by commenting `/confirm`."
    repro_line = ""
    if repro is not None:
        repro_line = "\n\n" + bug_repro.comment_for_outcome(repro.outcome)
    return (
        f":memo: I drafted a spec for this issue at {pr.url}.\n\n"
        f"{ask}{repro_line}\n\n"
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


def _payload_labels(issue_payload: dict) -> set[str]:
    """Pull label names out of a webhook issue payload."""
    out: set[str] = set()
    for label in issue_payload.get("labels", []) or []:
        if isinstance(label, str):
            out.add(label)
        elif isinstance(label, dict) and label.get("name"):
            out.add(str(label["name"]))
    return out


def _issue_handle(
    issue_payload: dict, *, issue_number: int, labels: tuple[str, ...],
) -> Issue:
    return Issue(
        number=issue_number,
        title=issue_payload.get("title", ""),
        body="",
        labels=labels,
        state=issue_payload.get("state", "open"),
        author=(issue_payload.get("user") or {}).get("login", ""),
        url=issue_payload.get("html_url", ""),
    )


def _refinement_ack_body(refined) -> str:
    parts = [
        ":memo: Updated the spec with your reply.",
        "",
        f"**What changed:** {refined.change_summary}",
    ]
    if refined.remaining_questions:
        parts.append("")
        parts.append(
            f"Anything else? {len(refined.remaining_questions)} open question(s) remain:"
        )
        parts.append("")
        for i, q in enumerate(refined.remaining_questions, 1):
            parts.append(f"{i}. {q}")
    else:
        parts.append("")
        parts.append("No open questions left — comment `/confirm` to proceed.")
    return "\n".join(parts)
