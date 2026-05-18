# Code Agent Charter

**Status:** Active
**Owner:** @your-org/agent-team
**Spec:** [docs/superpowers/specs/2026-05-16-code-agent-design.md](../../docs/superpowers/specs/2026-05-16-code-agent-design.md)

## 1. Identity

- Bot account: `code-agent-bot@<your-domain>`
- Signed commits
- PR title prefix: `[agent:code]`

## 2. Trigger

- Cron `0 */6 * * *` (every 6 hours).
- `pull_request.labeled` with `reporter-approved` on `agent/spec-*` (pre-review reports).

## 3. Allowed scope

- **Write:** `custom-addons/**` (with exceptions in §4), `docs/**`, test files everywhere.
- **Read:** all repo content.

## 4. Forbidden

- `.github/workflows/**`, `infra/**`, `Dockerfile`, `agents/charters/**`.
- `custom-addons/saas_*/security/**` without security-agent co-sign.
- Behaviour-changing refactors — must be behaviour-preserving or file an issue instead.
- Removing tests.

## 5. Caps

- ≤ 400 LOC per PR.
- ≤ 3 open PRs.
- Spend cap: USD 40 / week.

## 6. Loops

- **Test backfill** — see spec §5.1. Pick addon < 50% coverage; write tests.
- **Refactor** (duplicate code) — see spec §5.2. jscpd ≥ 0.85 similarity.
- **Manifest hygiene** — see spec §5.3.
- **README generation** — see spec §5.4. Weekly.
- **Dead-code** — see spec §5.5. 30-day mark-and-wait before removal.
- **Pre-review reports** — see spec §5.6. Triggered per Implementation Agent PR.

## 7. Escalation paths

- Flaky test produced → CI auto-detects; PR closed by human.
- Refactor changes behaviour → CI test failure; PR fails.
- Dead-code candidate has been marked < 30 days when removal attempted → blocked by audit.
- Pre-review report incorrect → reviewer rejects; loop tunes.

## 8. Kill switch

`AGENTS_ENABLED=false`. Backlog persists; resumes on re-enable.
