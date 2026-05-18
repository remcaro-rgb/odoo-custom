# Spec Generator Charter

**Status:** Active
**Owner:** @your-org/maintainers + @your-org/security-leads
**Spec:** [docs/superpowers/specs/2026-05-16-spec-generator-agent-design.md](../../docs/superpowers/specs/2026-05-16-spec-generator-agent-design.md)

## 1. Identity

- Bot account: `spec-generator-bot@<your-domain>`
- GPG-signed commits (key fingerprint TBD on first deploy)
- PR title prefix: `[agent:spec-generator]`

## 2. Trigger

- `issues.opened` and `issues.labeled` events on issues with label `feature-request` or `bug`.
- `issue_comment.created` events on issues with an open `agent/spec-*` PR.
- `issues.labeled` with `spec-refinement-needed` on a PR.
- Daily cron `0 1 * * *` for the auto-confirm sweep.
- Email-to-issue and chatbot-originated issues (with `source:chatbot` label) feed in transparently.

## 3. Allowed scope

- **Write:** `docs/superpowers/specs/**`, `docs/superpowers/plans/**` (outline-stub plans only), GitHub issue comments, PR comments, PR labels.
- **Read:** all repo content.

## 4. Forbidden

- Any path outside `docs/superpowers/`.
- Cannot apply the `intent-confirmed` label without either an explicit reporter `/confirm` OR 24h silence after the last spec revision.
- Cannot file an issue for a "sensitive" classification — those route to support inbox.

## 5. Caps

- Spend cap: USD 50 / week.
- Concurrent open PRs: 3 (queued otherwise).
- Iteration count per spec: no hard cap, but `iter > 10` is escalated.

## 6. Sequences

- **Initial draft** — see spec §5.1 (feature) or §5.2 (bug, with repro on agentlab).
- **Reporter iteration** — see spec §5.3. Apply clarifications; revise spec; comment back.
- **Auto-confirm sweep** — see spec §5.4. Daily cron.
- **Spec refinement** — see spec §5.5. Triggered by `spec-refinement-needed` label.

## 7. Escalation paths

- Sensitive topic detected → route to support inbox; no spec drafted.
- Reporter silent > 14 days → abandon (label `abandoned`).
- Prompt injection detected → refuse + log to security audit queue.
- Confidence < 0.5 → ask clarifying questions instead of drafting.

## 8. Kill switch

Set repo variable `AGENTS_ENABLED=false`. The workflow checks this at entry; new triggers are dropped until re-enabled. In-flight drafts complete normally.
