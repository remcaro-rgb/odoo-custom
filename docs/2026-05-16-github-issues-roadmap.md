# GitHub Issues Roadmap — v8

**Date:** 2026-05-16
**Purpose:** Convert the v8 plan's 10-phase roadmap into actionable GitHub issues, ready to drop into a project board.

Each phase is an **epic** (single issue with a checklist of sub-issues). Sub-issues track concrete deliverables and acceptance criteria. Use the labels documented at the bottom of this file.

The order matters: phases are listed in execution order. Within a phase, issues are roughly serial but can parallelise.

---

## Phase 1 — Spec workflow enforcement (week 1)

### Epic: Phase 1 · Spec workflow enforcement
**Labels:** `epic`, `phase:1`

> Lock in the spec-driven workflow before any agent work begins. Templates, ADR folder, CODEOWNERS, PR template, `spec-required` CI gate.

**Sub-issues:**
- [ ] [P1.1] Ship spec & plan templates → `docs/superpowers/specs/_TEMPLATE-design.md`, `_TEMPLATE-fix.md`, `docs/superpowers/plans/_TEMPLATE.md`. ✅ delivered in v8.
- [ ] [P1.2] Create `docs/adr/` with README + first three ADRs. ✅ delivered.
- [ ] [P1.3] Land `.github/CODEOWNERS`. Replace `@your-org/*` placeholders with real team handles. ✅ scaffold delivered.
- [ ] [P1.4] Land `.github/PULL_REQUEST_TEMPLATE.md` with the v6 checklist. ✅ delivered.
- [ ] [P1.5] Land `.github/workflows/spec-required.yml`. ✅ delivered.
- [ ] [P1.6] Land `.github/workflows/agent-guardrails.yml`. ✅ delivered.
- [ ] [P1.7] Create GitHub teams: `maintainers`, `security-leads`, `prod-deployers`, `agent-team`, `senior-engineers`, plus per-addon owners (`club-addon-owners`, `accounting-addon-owners`, `colombia-localization`).
- [ ] [P1.8] Configure branch protection on `main`: require PR, require `spec-required` + `agent-guardrails` checks, require CODEOWNERS approval, refuse force-push and history rewrite.
- [ ] [P1.9] Configure branch protection on `agent/spec-*`: refuse force-push, require signed commits, require CI.
- [ ] [P1.10] Provision repo variable `AGENTS_ENABLED=true` (the kill switch — flip to `false` to pause every agent).

---

## Phase 2 — Test ladder hardening (weeks 2–3)

### Epic: Phase 2 · Test ladder hardening
**Labels:** `epic`, `phase:2`

> Beef up Gate 1 (PR → main) and Gate 2 (main → staging) so every change passes meaningful quality bars before reaching prod.

**Sub-issues:**
- [ ] [P2.1] Gate 1: add `lint-python` job (`ruff` + `black --check`).
- [ ] [P2.2] Gate 1: add `lint-odoo-manifest` job (every changed manifest parses + version bumped if `models/` touched).
- [ ] [P2.3] Gate 1: add `lint-xml` (xmllint on changed views/data/security XML).
- [ ] [P2.4] Gate 1: add `security-scan` (`bandit` + `trivy fs` Dockerfile + `gitleaks` PR diff).
- [ ] [P2.5] Gate 1: add `test-changed-addons` (auto-detect, run pytest on those addons only).
- [ ] [P2.6] Gate 1: add `schema-diff` (informational; posts to PR).
- [ ] [P2.7] Gate 2: add smoke probes (`/web/health` + login flow on a known staging tenant).
- [ ] [P2.8] Gate 2: add `migration-dry-run` (clone one representative staging tenant, run `-u all`).
- [ ] [P2.9] Gate 2: add `addon-upgrade-matrix` (for each `saas_*` addon: install-fresh → install-on-existing → upgrade).
- [ ] [P2.10] Document the test patterns in `docs/runbooks/writing-addon-tests.md`.
- [ ] [P2.11] Backfill at least one passing test for every `saas_*` addon (currently only `saas_tenant_gate` has tests).

---

## Phase 3 — Production environments (weeks 4–5)

### Epic: Phase 3 · Production environments
**Labels:** `epic`, `phase:3`

> Stand up the two production environments + promote/rollback/hotfix workflows.

**Sub-issues:**
- [ ] [P3.1] Provision Railway prod project + Postgres + Traefik. Configure secrets per `infra/railway/` patterns.
- [ ] [P3.2] Provision Fly app `odoo-saas-odoo-prod` + Postgres. Configure secrets.
- [ ] [P3.3] Wildcard DNS + cert: `*.<your-domain>` for tenant subdomains; `preview-*.<your-domain>` for preview envs.
- [ ] [P3.4] Land `.github/workflows/promote-to-prod.yml`. ✅ scaffold delivered.
- [ ] [P3.5] Land `.github/workflows/rollback-prod.yml`. ✅ scaffold delivered.
- [ ] [P3.6] Create `hotfix-prod.yml` (similar to promote, abbreviated Gate 1, N=2 approval, 48h retro fix-brief commitment).
- [ ] [P3.7] Configure GitHub Environments: `prod-rollout` (N=1), `prod-rollout-strict` (N=2), `prod-rollback` (N=2), `prod-hotfix` (N=2), `prod-railway`, `prod-fly`.
- [ ] [P3.8] Extend `saas_tenant_gate.tenant` model with `pool_id`, `wave`, `last_migrated_sha` fields (per main plan §3.3).
- [ ] [P3.9] Migrate first 1–2 friendly tenants to `wave=canary` for canary testing.
- [ ] [P3.10] Land `infra/runbooks/promote-to-prod.md` (operator runbook).
- [ ] [P3.11] Land `infra/runbooks/rollback-prod.md` and `hotfix-prod.md`.
- [ ] [P3.12] Test: weekly rollback rehearsal cron (dry-run against agentlab tenant pool).

---

## Phase 4 — Per-client rollout polish (week 6)

### Epic: Phase 4 · Per-client rollout polish
**Labels:** `epic`, `phase:4`

> Add the per-tenant migration queue + size buckets + maintenance windows + feature flags wired to waves.

Implements: `docs/superpowers/specs/2026-05-16-tenant-migration-queue-design.md`.

**Sub-issues:**
- [ ] [P4.1] Create `saas.tenant.migration.job` model + view in `saas_tenant_gate`.
- [ ] [P4.2] Implement the migration runner (Python + `psql -c` + `subprocess.run(['odoo', '-u', 'all'])`).
- [ ] [P4.3] Add `size_bucket` field on `saas.tenant`; daily cron to refresh from DB size.
- [ ] [P4.4] Add `maintenance_window` cron field (default `0 2 * * *`) + `tz` field.
- [ ] [P4.5] Wire feature-flag flip into `promote-to-prod.yml` (per wave).
- [ ] [P4.6] Wire migration queue into `promote-to-prod.yml` (replace inline migration loop).
- [ ] [P4.7] Add `data-integrity` check (row-count drift in `account_move`, `sale_order`, `stock_move`, `account_payment` pre/post migration).
- [ ] [P4.8] Add `prod-readiness` soak-time gate (24h for risk:low/medium, 72h for risk:high).
- [ ] [P4.9] Document large-tenant migration safety practices in `docs/runbooks/large-tenant-migrations.md`.

---

## Phase 5 — Observability & agentlab (weeks 7–8)

### Epic: Phase 5 · Observability & agentlab
**Labels:** `epic`, `phase:5`

> Central log drain, per-tenant metrics, audit log + nightly export, agentlab Fly app with masked daily restore.

Implements: `docs/superpowers/specs/2026-05-16-observability-stack-design.md` + `2026-05-16-agentlab-environment-design.md`.

**Sub-issues:**
- [ ] [P5.1] Sign up Better Stack; create per-source tokens.
- [ ] [P5.2] Wire Odoo workers to ship structured JSON logs to stdout; Fly + Railway log drains forward to Better Stack.
- [ ] [P5.3] Define log shape (every line carries `tenant`, `worker`, `request_id`, `agent?`, `run_id?`).
- [ ] [P5.4] Build Grafana per-tenant dashboard template (login rate, p95, 5xx, workers, DB conns).
- [ ] [P5.5] Wire alerts (5xx burst, migration fail, backup staleness, agent spend, parity drift, ...).
- [ ] [P5.6] Create `saas.audit.event` model with append-only triggers + nightly S3 Object Lock export.
- [ ] [P5.7] Provision Fly app `odoo-saas-odoo-agentlab` + Fly Postgres `odoo-saas-odoo-agentlab-db`.
- [ ] [P5.8] Implement `infra/agentlab/mask-prod-data.sh` (allow-list masking; reuse for nightly restore).
- [ ] [P5.9] Land `infra/agentlab/mask-allowlist.yml` and `infra/agentlab/sensitive-topics.yml` (owned by `security-leads`).
- [ ] [P5.10] Implement nightly restore cron `agentlab-daily-restore.yml`.
- [ ] [P5.11] Wire agentlab smoke probe + freshness alert (snapshot age > 30h → page).
- [ ] [P5.12] Configure egress firewall on agentlab Fly app (SMTP → MailHog, telemetry → mock, webhooks → mock).

---

## Phase 6 — Portable agent runtime (weeks 9–10)

### Epic: Phase 6 · Portable agent runtime
**Labels:** `epic`, `phase:6`

> Build the hexagonal runtime that all six agents will sit on. Default adapters for day-one bindings.

Implements: `docs/superpowers/specs/2026-05-16-portable-agent-runtime-design.md`.

**Sub-issues:**
- [ ] [P6.1] `agents/` package skeleton with pyproject + Dockerfile. ✅ delivered.
- [ ] [P6.2] All 10 port ABCs implemented and tested. ✅ delivered.
- [ ] [P6.3] Default adapters: `secrets_envvar`, `logger_stdjson`, `llm_litellm`. ✅ delivered.
- [ ] [P6.4] Remaining default adapters: `repo_github`, `issues_github`, `notifier_slack`, `artifacts_s3`, `compute_fly`, `kb_pgvector`, `events_github_webhook`.
- [ ] [P6.5] CLI: `agents run`, `agents iterate`, `agents handle-commit`, `agents config validate`, `agents test-adapter`. ✅ delivered.
- [ ] [P6.6] Contract test suite per port. ✅ scaffolded.
- [ ] [P6.7] Integration test suite (live credentials, nightly).
- [ ] [P6.8] Build + push OCI image to `ghcr.io/<org>/odoo-saas-agents:v0.1.0`.
- [ ] [P6.9] One smoke agent ("hello world") running end-to-end on the runtime — proves the wiring.
- [ ] [P6.10] Cosign signing + SBOM emission for releases.

---

## Phase 7 — Spec Generator (weeks 11–12)

### Epic: Phase 7 · Spec Generator agent
**Labels:** `epic`, `phase:7`

Implements: `docs/superpowers/specs/2026-05-16-spec-generator-agent-design.md`.

**Sub-issues:**
- [ ] [P7.1] Implement `agents/agents/spec_generator/` modules: core, intake, classifier, repro, drafter, refiner, dup_detector, commenter.
- [ ] [P7.2] Workflow `.github/workflows/spec-generator.yml` (issues.opened + labeled).
- [ ] [P7.3] Workflow `.github/workflows/spec-generator-iterate.yml` (issue_comment.created).
- [ ] [P7.4] Workflow `.github/workflows/spec-generator-sweep.yml` (daily auto-confirm sweep).
- [ ] [P7.5] Bug repro path on agentlab (Playwright-based).
- [ ] [P7.6] Land `.github/workflows/spec-quality.yml`. ✅ delivered.
- [ ] [P7.7] Service account `spec-generator-bot@<your-domain>` with signed commits.
- [ ] [P7.8] Slack `/spec` command via Zapier (interim per v6 Q7) or bot.
- [ ] [P7.9] Canary rollout: shadow mode → test label → all `feature-request` → `bug`.
- [ ] [P7.10] First labelled set of 100 issues for classifier accuracy test.

---

## Phase 8 — Implementation Agent + preview infra (weeks 13–15)

### Epic: Phase 8 · Implementation Agent + preview infra
**Labels:** `epic`, `phase:8`

Implements: `docs/superpowers/specs/2026-05-16-implementation-agent-design.md`.

**Sub-issues:**
- [ ] [P8.1] Implement `agents/agents/implementation/` modules: core, planner, coder, gate1, preview, classifier, commenter, state_machine.
- [ ] [P8.2] Implement `infra/fly/preview/`: `spawn.sh`, `seed.sh`, `make-reviewer.sh`, `redeploy.sh`.
- [ ] [P8.3] Workflow `.github/workflows/implementation.yml` (label `intent-confirmed`).
- [ ] [P8.4] Workflow `.github/workflows/implementation-iterate.yml` (comments + labels).
- [ ] [P8.5] Workflow `.github/workflows/notify-reporter-on-human-commit.yml` (v5 Q15).
- [ ] [P8.6] Workflow `.github/workflows/implementation-sweep.yml` (daily stale-PR sweep).
- [ ] [P8.7] Land `.github/workflows/preview-cleanup.yml`. ✅ scaffold delivered.
- [ ] [P8.8] Service account `implementation-bot@<your-domain>` with signed commits.
- [ ] [P8.9] Wildcard cert `preview-*.<your-domain>` + Traefik routing.
- [ ] [P8.10] Test fixtures: 5 specs with deliberate issues for E2E testing.
- [ ] [P8.11] Canary rollout: shadow → test fixtures → opt-in → default-on (2 weeks each).

---

## Phase 9 — Code · Security · Optimization (weeks 16–19)

### Epic: Phase 9 · Improvement agents
**Labels:** `epic`, `phase:9`

> Three autonomous improvement agents. Security must be online by end of week 18 because it provides pre-review reports for Implementation Agent PRs.

Implements: `2026-05-16-code-agent-design.md`, `2026-05-16-security-agent-design.md`, `2026-05-16-optimization-agent-design.md`.

**Sub-issues:**
- [ ] [P9.1] Implement Code Agent loops (test backfill, refactor, manifest, README, dead-code, pre-review).
- [ ] [P9.2] Implement Security Agent loops (dependency, bandit, Odoo rules, record-rules, gitleaks, tenancy, pre-review).
- [ ] [P9.3] Implement Optimization Agent loops (slow-query, computed-field, N+1, image-size, cron, worker-pressure).
- [ ] [P9.4] Service accounts: `code-agent-bot`, `security-agent-bot`, `optimization-agent-bot`.
- [ ] [P9.5] Pre-review report integration into Implementation Agent's `awaiting-human-review` flow.
- [ ] [P9.6] CVE webhook subscription (GitHub Advisory) for Security Agent's critical-CVE hotfix path.
- [ ] [P9.7] Optimization Agent benchmark.run() deterministic (≥3 consistent runs required).
- [ ] [P9.8] Allow-list maintenance pipeline for Security Agent.
- [ ] [P9.9] Canary rollouts per agent: shadow → 1 PR cap → 3 PR cap (2 weeks each).

---

## Phase 10 — Support Triage Agent (weeks 20–28)

### Epic: Phase 10 · Support Triage Agent
**Labels:** `epic`, `phase:10`

Implements: `docs/superpowers/specs/2026-05-16-support-triage-agent-design.md`.

**Sub-issues (sub-phased):**

**10a · MVP (weeks 20–22)**
- [ ] [P10.1] Build `custom-addons/saas_support_chatbot` addon: models, controllers, qweb widget.
- [ ] [P10.2] Provision Fly app `odoo-saas-support-gateway` + Postgres.
- [ ] [P10.3] Implement gateway endpoints `/v1/triage`, `/v1/file-issue`.
- [ ] [P10.4] KB ingest: 43 addon READMEs + `docs/obsidian/` + `docs/superpowers/specs/` → pgvector.
- [ ] [P10.5] PII-mask pipeline (3-layer: deny-list → tenant allow-list → LLM pass).
- [ ] [P10.6] HMAC auth between addon and gateway; quarterly rotation.
- [ ] [P10.7] Add `support_chatbot_enabled` flag to `saas_tenant_gate`.
- [ ] [P10.8] Canary on 2 friendly tenants for 2 weeks.

**10b · Back-sync (weeks 23–24)**
- [ ] [P10.9] Gateway endpoint `/v1/webhook-inbound` for GitHub webhook events.
- [ ] [P10.10] Bidirectional sync: PR state → chat thread comments.
- [ ] [P10.11] Bilingual ES/EN reply rendering.

**10c · In-chat /approve (weeks 25–26)**
- [ ] [P10.12] [Approve] + [Iterate] buttons in chat → forward to GitHub.

**10d · Per-tenant context (weeks 27–28)**
- [ ] [P10.13] Bot reads recent errors from `ir.logging` (per user).
- [ ] [P10.14] Bot reads current Odoo view from session context.
- [ ] [P10.15] Workaround suggestions informed by current state + feature flags.

---

## Phase 11 (optional) — Alternative-stack validation

### Epic: Phase 11 · Alternative-stack twin
**Labels:** `epic`, `phase:11`, `optional`

> Prove portability is real. Stand up a twin of the staging pipeline on GitLab + GPT-4o + Teams; run weekly smoke.

**Sub-issues:**
- [ ] [P11.1] Implement remaining adapters: `repo_gitlab`, `issues_gitlab`, `notifier_teams`, `llm_openai_direct`.
- [ ] [P11.2] Mirror the repo to a GitLab instance (read-only mirror or active).
- [ ] [P11.3] Create `.gitlab-ci.yml` equivalents for `ci.yml`, `promote-to-prod.yml`, `agent-guardrails.yml`.
- [ ] [P11.4] Wire GitLab webhooks → gateway events endpoint.
- [ ] [P11.5] Weekly smoke job exercises the full alt-stack path.
- [ ] [P11.6] Quarterly migration drill: actually run a real PR through the alt stack.

---

## Labels glossary

| Label | Meaning |
|---|---|
| `epic` | Tracks a whole phase |
| `phase:N` | Belongs to phase N |
| `feature-request` | Triggers Spec Generator |
| `bug` | Triggers Spec Generator |
| `source:chatbot` | Filed by Support Triage Agent |
| `spec-drafted`, `awaiting-reporter-confirm`, `intent-confirmed`, `implementing`, `awaiting-reviewer`, `iterating`, `reporter-approved`, `awaiting-human-review`, `human-refining`, `human-review-approved`, `awaiting-reporter-reconfirm`, `awaiting-devops`, `merged`, `rolling-out`, `done`, `needs-human`, `abandoned` | PR lifecycle (Implementation Agent state machine) |
| `risk:low`, `risk:medium`, `risk:high` | Determines soak time; auto-applied |
| `spec-exempt` | Only admins can apply; bypasses spec-required check |
| `tenancy-boundary` | Issue: requires human review by `security-leads` |
| `needs-repro-info`, `needs-fixture`, `repro-confirmed` | Spec Generator bug-repro outcomes |
| `[possible-dup]` | Spec Generator dup-detection result (in PR title) |
| `spec-refinement-needed` | Triggers Spec Generator to refine an in-flight spec |
| `agent-bypass-guardrails` | Admin-only label permitting an agent to touch normally-forbidden paths |
| `infra-issue` | Preview env spawn / deployment failure |
| `incident-followup` | Security findings of secrets-in-code |
| `tests-required-for-changes` | Implementation didn't add a test where it should have |
