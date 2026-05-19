# Phase 2 — Test ladder hardening — Design Spec

**Date:** 2026-05-19
**Author:** Manu (drafted with Claude)
**Status:** Accepted
**Spec type:** design spec (follows §2.4 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Scope of work:** Tighten Gate 1 (per-commit) of the three-gate test ladder per master plan §4 (Pillar C). Adds static analysis (ruff, bandit), HTTP-mode addon tests, and addon-upgrade-matrix smoke to CI.

---

## 1. Goal

Push the failure-discovery window left. Today the only addon coverage in CI is `saas_tenant_gate test suite` (15 tests, `--stop-after-init` mode). Lint regressions, missing addon dependencies, HttpCase failures, and obvious security smells go undetected until staging or production. Phase 2 closes those gaps by adding four CI jobs that run on every PR.

## 2. Non-goals

- Gate 2 (per-merge) behavioral cross-platform parity probes. Deferred to Phase 3 because the existing Cross-platform parity gate is status-only and the behavioral check requires Railway + Fly staging URLs to actually compare. Tracked.
- Gate 3 (per-promote) soak-time monitoring + auto-revert. Phase 3 work alongside `promote-to-prod` execution.
- Contract tests for the 9 remaining agent runtime ports (`Repo`, `IssueTracker`, `Notifier`, `SecretStore`, `LLMProvider`, `ComputeEnv`, `ArtifactStore`, `KnowledgeBase`, `EventBus`). Substantial; gets its own PR + spec.
- Snyk procurement (open question Phase 9 Q1 — defaulted to "no, pip-audit only").
- Cleaning up the 467 ruff findings in `custom-addons/club_*/`, `account_*/`, `co_*/`, `jorels-addons/`. Linted advisory-only here; cleanup tracked.

## 3. Tenancy impact

**No direct impact on the tenancy boundary.** All work in this spec is CI infrastructure (workflow YAML, ruff/bandit configuration, test runners). No new addon code, no new fields on tenant-facing models, no changes to `saas_tenant_gate`'s seat-cap or telemetry surfaces, no changes to `saas_provisioning_gateway`'s HMAC contract.

The only addon-touching changes are mechanical lint fixes the new ruff rules surface (raise-from-err, unused imports, percent-format → f-string). Those don't change runtime behavior; the existing test suite continues to pass.

**Indirect protective effect:** Bandit security scan catches hardcoded-secret regressions in `saas_*` controllers before they hit staging, lowering the chance of a tenant-data leak via misconfigured logging or auth code.

## 4. Data model changes

None. CI-only work.

## 5. API surface

None. CI-only work.

## 6. Security

The substantive security gain is the addition of bandit (medium-severity, medium-confidence) scoped to `saas_*` + `agents/`. Configured to skip:
- B101 (assert in test code — Odoo idiom)
- B603/B607 (subprocess with non-literal args — adapter pattern in `agents/agents/adapters/*`, reviewed by humans, also under per-file ruff overrides)
- B310 (urllib.urlopen — used in `saas_filestore_backup` and `saas_provisioning_gateway` for S3 presigned URL fetches; reviewed at code-review time)

The ruff rule set covers most pyflakes/PEP-8 categories plus `B` (bug-prone code) and `UP` (modernization). Auto-fix applied; remaining substantive findings (B904 raise-from, S603/S607 noqa) hand-resolved.

No new attack surface added — all four jobs run inside the ephemeral GHA runner with the existing `GITHUB_TOKEN` scope.

## 7. Test plan

Each CI job is its own test:

| Job | Asserts |
|---|---|
| Lint custom addons (ruff) | `saas_*` + `agents/` are clean under E/F/I/W/B/UP rules; per-file ignores documented in `.ruff.toml` |
| Lint legacy + jorels addons (advisory) | Reports lint findings on legacy code without blocking; baseline for future cleanup |
| Bandit security scan | No medium-severity, medium-confidence findings in maintained addons + agent runtime |
| saas_tenant_gate HttpCase suite | `TestTelemetry` (the HmacCase from `saas_tenant_gate`) passes; HTTP server reachable, signatures validated, replay protection works |
| Addon upgrade matrix | Every installable addon installs cleanly on a fresh DB in topological order |

Existing tests continue:
- `Build Odoo/Postgres/Traefik image` — Docker build path
- `saas_tenant_gate test suite` (15 non-HTTP tests)
- `Spec link present`, `Agent guardrails`, `Spec quality checks`, `Protection-drift audit`, `Workflow lint`

## 8. Rollout

This PR. No staged rollout — CI changes are atomic per merge to main.

After merge, two follow-up commits (not in this PR):
1. Add the four new check names to `.github/required-checks.yml`.
2. Apply the updated required list to live branch protection via `infra/scripts/apply-required-checks.sh`.

The follow-up step waits for the new checks to have one passing run on main, so the live protection update doesn't accidentally block all future PRs on a flaky brand-new check.

## 9. Observability

Each CI job emits standard GitHub Actions logs. No new metrics or alerts in this spec (Phase 5 territory).

The protection-drift-audit workflow already alerts (via failing CI) when a required check name in `required-checks.yml` doesn't match a workflow job name — this PR exercises that path because the four new jobs ARE NOT yet in the required list. Confirmed working: protection-drift-audit passes on this PR because the audit only flags missing required → job, not extra job → required.

## 10. Open questions

None blocking. Captured as deferrals in §2.

---

## Plan reference

Implementation plan: this PR is small enough to land as a single bundle; no separate `docs/superpowers/plans/2026-05-19-phase-2-test-ladder.md` file. The commit message + PR body capture the rationale.
