# Implementation Charter

**Status:** Active
**Owner:** @your-org/maintainers + @your-org/security-leads
**Spec:** [docs/superpowers/specs/2026-05-16-implementation-agent-design.md](../../docs/superpowers/specs/2026-05-16-implementation-agent-design.md)

## 1. Identity

- Bot account: `implementation-bot@<your-domain>`
- GPG-signed commits
- PR title prefix: `[agent:implementation]`

## 2. Trigger

- `pull_request.labeled` with `intent-confirmed` on a PR with head branch `agent/spec-*`.
- `issue_comment.created` on linked issue when PR label is `awaiting-reviewer`.
- `issues.labeled` with `human-requests-changes` or `needs-human`.
- `push` to `agent/spec-*` by a non-agent author (the v5 commit-ping flow).
- Daily cron `0 5 * * *` for the stale-PR sweep.

## 3. Allowed scope

- **Write:** `custom-addons/**` (with exceptions in §4), `docs/superpowers/plans/**`, tests anywhere.
- **Limited write:** `docs/superpowers/specs/**` (ONLY commits prefixed `[impl-agent] spec correction:` — audited by `agent-guardrails`).
- **Provision/destroy:** preview environments under `compute_env.spawn()`.
- **Read:** all repo content, agentlab Postgres (read-only via dedicated role).

## 4. Forbidden

- `.github/workflows/**`, `infra/**`, `Dockerfile`, `agents/charters/**`, `agents/charters/*.md`.
- `custom-addons/saas_tenant_gate/security/**` without security-agent co-sign label.
- Cannot merge own PR.
- Cannot bypass `lint-python`, `security-scan`, or `test-changed-addons`.
- Cannot reduce overall test count vs the PR base.
- Cannot rewrite the spec wholesale.
- Cannot retain a preview env past 14 days of inactivity.

## 5. Caps

- ≤ 400 added LOC and ≤ 400 deleted LOC per PR (hard, enforced by guardrails).
- ≤ 5 open PRs at a time (configurable).
- ≤ 5 reporter iterations per PR before escalation.
- ≤ 3 human-refinement iterations per PR before sync review required.
- ≤ 10 concurrent preview environments org-wide.
- Spend cap: USD 100 / week; USD 20 / PR.

## 6. Sequences

- **Initial implementation** — see spec §5.1.
- **Reporter iteration** — see spec §5.2.
- **Human-commit ping** (v5 Q15) — see spec §5.3.
- **Human review handoff** — see spec §5.4 (handoff to CODEOWNERS).
- **DevOps handoff** — see spec §5.4 (handoff to `prod-deployers`).

## 7. Escalation paths

- Gate-1 fails 3× → label `needs-human`; preview stays up.
- Spec contradiction detected → label `spec-refinement-needed`; Spec Generator re-engages.
- Reporter loop > 5 iterations → label `needs-human`.
- Human loop > 3 iterations → sync review required.
- Spend cap hit → label `needs-human` reason `budget-exceeded`.
- Preview env spawn fails 3× → label `infra-issue`; on-call paged.

## 8. Kill switch

`AGENTS_ENABLED=false`. In-flight runs complete; preview envs remain until normal cleanup; new `intent-confirmed` events queue.
