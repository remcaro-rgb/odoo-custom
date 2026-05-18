# Optimization Agent Charter

**Status:** Active
**Owner:** @your-org/agent-team
**Spec:** [docs/superpowers/specs/2026-05-16-optimization-agent-design.md](../../docs/superpowers/specs/2026-05-16-optimization-agent-design.md)

## 1. Identity

- Bot account: `optimization-agent-bot@<your-domain>`
- Signed commits
- PR title prefix: `[agent:optimization]`

## 2. Trigger

- Cron `0 4 * * *` (daily 04:00 UTC, after agentlab snapshot is fresh).

## 3. Allowed scope

- **Write:** `custom-addons/**` (indexes, computed-field tweaks, batch reads, ir.cron tuning), `custom-addons/**/migrations/**`.
- **Read:** agentlab Postgres (read-only via dedicated role), Fly + Railway metrics APIs.

## 4. Forbidden

- `Dockerfile` (issue-only — security-leads own it).
- `.github/workflows/**`, `infra/**`, `agents/charters/**`.
- Worker-count autotuning (recommendations only).
- Premature optimisation — must point at a measured problem.

## 5. Caps

- ≤ 400 LOC per PR.
- ≤ 3 open PRs.
- Spend cap: USD 30 / week.

## 6. Loops

- **Slow query** — see spec §5.1. Daily, top 5 by total_exec_time.
- **Computed field** — see spec §5.2. Every 12h.
- **N+1** — see spec §5.3. Weekly canonical-workflow instrumentation.
- **Image size** — see spec §5.4. Weekly, issue-only.
- **Cron tuning** — see spec §5.5. Daily.
- **Worker pressure** — see spec §5.6. Daily, issue-only.

## 7. Escalation paths

- Benchmark non-deterministic → require ≥ 3 consistent runs before reporting.
- Proposed change slows other queries → bench catches; PR fails.
- store=True breaks computed correctness → existing tests catch.

## 8. Kill switch

`AGENTS_ENABLED=false`. Backlog persists.
