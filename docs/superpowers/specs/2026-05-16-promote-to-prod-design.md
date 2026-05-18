# Promote-to-prod, Rollback, and Hotfix Workflows — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** `.github/workflows/promote-to-prod.yml`, `rollback-prod.yml`, `hotfix-prod.yml`. The complete prod-rollout machinery.

---

## 1. Goal

Concrete, well-tested workflows that:

- Promote a SHA from staging to prod on a per-wave basis (canary → w1 → w2).
- Roll back to a previous prod tag for a wave when something's wrong.
- Apply emergency hotfixes for severity ≥ high incidents, with N=2 approval and a 48h retro fix-brief commitment.
- Enforce cross-platform parity (Railway + Fly must both succeed).
- Run per-tenant migrations via the `saas.tenant.migration.job` queue.
- Flip feature flags per wave.
- Audit every action.

---

## 2. Non-goals

- Automatic rollback decisions. Humans decide when to roll back.
- Wave-skipping. The order canary → w1 → w2 is enforced; no jumping straight to w2 (except `wave=all` for emergencies).
- Per-tenant promote (single tenant outside a wave). Use `wave=canary` with that tenant set to canary, then revert.
- Cross-stack promote (promote Railway-only or Fly-only). Parity gate enforces both.

---

## 3. Workflow: `promote-to-prod.yml`

```yaml
name: promote-to-prod

on:
  workflow_dispatch:
    inputs:
      sha:
        description: 'Commit SHA to promote (default: latest green on main)'
        required: false
      wave:
        description: 'Wave to promote'
        required: true
        type: choice
        options: [canary, w1, w2, all]
      platforms:
        description: 'Platforms to deploy to (comma-separated)'
        default: 'railway,fly'
      dry_run:
        description: 'Dry-run mode'
        default: 'true'
        type: choice
        options: ['true', 'false']

jobs:
  preflight:
    # 1. Resolve SHA (default = latest green on main per ci.yml)
    # 2. Assert SHA has passed Gate 1 + Gate 2
    # 3. Assert soak time elapsed:
    #      risk:low|medium  → ≥ 24h since merge to main
    #      risk:high        → ≥ 72h since merge to main
    # 4. Assert no open rollback for this wave in last 7 days
    # 5. Assert AGENTS_ENABLED + AGENT_PROMOTE_ENABLED are true
    # 6. List tenants in target wave (from saas.tenant)
    # 7. Compute migration deltas (tenants where last_migrated_sha != target)

  approval:
    # GitHub Environment 'prod-railway' and 'prod-fly' require approval from
    # prod-deployers team (N=1 for normal promote).
    # For wave=all, N=2.
    needs: [preflight]
    environment: prod-rollout
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "Awaiting approval from prod-deployers..."
          # GitHub Environments enforce this; the job is a placeholder.

  tag-image:
    # Tag the image at <sha> as prod-YYYY.MM.DD-N and push.
    needs: [approval]

  deploy-railway:
    if: contains(inputs.platforms, 'railway')
    needs: [tag-image]
    environment: prod-railway
    # Rolling deploy via railway CLI.

  deploy-fly:
    if: contains(inputs.platforms, 'fly')
    needs: [tag-image]
    environment: prod-fly
    # Rolling deploy via flyctl.

  parity-gate:
    needs: [deploy-railway, deploy-fly]
    # Hard-fail if one platform succeeded while the other didn't.

  queue-migrations:
    needs: [parity-gate]
    # For each tenant in target wave where last_migrated_sha != target:
    #   INSERT INTO saas.tenant.migration.job (tenant_id, target_sha, status='queued')

  run-migrations:
    needs: [queue-migrations]
    strategy:
      matrix:
        # One job per tenant (size-bucketed; smallest first per migration safety spec)
        tenant: <generated-list>
    # For each tenant:
    #   1. Take pgbackrest snapshot ≤ 4h old (per tenant migration safety §3.5)
    #   2. Respect maintenance_window if defined
    #   3. Run `odoo -u all -d <tenant>`
    #   4. On success: update tenant.last_migrated_sha; set job status='done'
    #   5. On failure: set job status='failed'; record error_excerpt; alert on-call;
    #      DO NOT block other tenants in the wave

  flip-feature-flags:
    needs: [run-migrations]
    # For each feature flag with wave-rollout enabled:
    #   Toggle 'on' for tenants in the current wave

  smoke:
    needs: [flip-feature-flags]
    # /web/health probe per tenant in wave; login test on a sample;
    # critical-paths E2E (Playwright) on one canary

  audit:
    if: always()
    needs: [smoke]
    # Write saas.audit.event rows: actor, target, sha, wave, dry_run, outcome
    # Notify Slack #devops-deploys with summary + rollback command snippet

  notify:
    if: always()
    needs: [audit]
    # Final Slack summary, paging on failure
```

### Approval flow detail

- For canary or w1: N=1 from `prod-deployers`. GitHub Environment `prod-rollout` requires 1 reviewer.
- For w2 or `all`: N=2 from `prod-deployers`. Achieved by using a stricter environment `prod-rollout-strict`.
- For hotfix: see `hotfix-prod.yml` below.

### Dry-run mode

When `dry_run=true`:
- Steps 1–7 (preflight) run normally.
- Approval is still required (so we exercise that path).
- Deploy steps run with `--dry-run` flag (Railway/Fly support this).
- Migrations run as `EXPLAIN` only.
- Smoke is skipped.
- Audit row carries `dry_run=true`.

---

## 4. Workflow: `rollback-prod.yml`

```yaml
name: rollback-prod

on:
  workflow_dispatch:
    inputs:
      target_sha:
        description: 'SHA to roll back TO (must be a prior prod tag)'
        required: true
      wave:
        description: 'Wave to roll back'
        required: true
        type: choice
        options: [canary, w1, w2, all]
      platforms:
        default: 'railway,fly'
      restore_data:
        description: 'Restore tenant data to pre-promotion snapshot? (destructive schema only)'
        default: 'false'
        type: choice
        options: ['true', 'false']
      paste_back_confirmation:
        description: 'Type "ROLLBACK <wave>" to confirm'
        required: true

jobs:
  preflight:
    # 1. Verify target_sha was previously deployed to prod (search tags)
    # 2. Verify paste_back_confirmation matches "ROLLBACK <wave>"
    # 3. Compute data-restore impact: which tenants have schema-forward-only
    #    migrations since target_sha?

  approval:
    needs: [preflight]
    environment: prod-rollback   # N=2 prod-deployers required

  tag-rollback:
    needs: [approval]
    # Tag the action: rollback-prod-YYYY.MM.DD-N pointing at target_sha

  deploy:
    needs: [tag-rollback]
    # Rolling deploy of target_sha to the named platforms

  tenant-restore:
    if: inputs.restore_data == 'true'
    needs: [deploy]
    strategy:
      matrix:
        tenant: <list>
    # For each tenant in wave that has schema-forward changes:
    #   Restore pre-promotion pgbackrest snapshot
    #   Update last_migrated_sha to target_sha

  smoke:
    needs: [deploy, tenant-restore]

  audit:
    if: always()
    needs: [smoke]
    # Write rollback events to saas.audit.event with reason from paste-back

  notify:
    if: always()
    needs: [audit]
    # Slack #devops-deploys + page on-call
```

**Why paste-back confirmation:** rollbacks are rare and high-risk. Forcing the operator to literally type `ROLLBACK w1` makes "I clicked the wrong button" 100× less likely.

**Why operator-opt-in data restore:** rolling forward a schema with destructive changes ≠ rolling back data. We refuse to auto-restore data because that's a separate decision the operator needs to make consciously.

---

## 5. Workflow: `hotfix-prod.yml`

```yaml
name: hotfix-prod

on:
  workflow_dispatch:
    inputs:
      hotfix_branch:
        description: 'Branch name (must start with hotfix/)'
        required: true
      target_sha:
        description: 'Commit SHA on the hotfix branch'
        required: true
      paste_back_confirmation:
        description: 'Type "HOTFIX <severity>" to confirm'
        required: true
      severity:
        description: 'Severity classification'
        required: true
        type: choice
        options: [high, critical]
      retro_brief_commitment:
        description: 'I commit to filing a retro fix-brief within 48h or reverting'
        required: true
        type: boolean

jobs:
  preflight:
    # 1. Assert hotfix_branch starts with 'hotfix/'
    # 2. Assert paste_back matches "HOTFIX <severity>"
    # 3. Assert retro_brief_commitment is true
    # 4. Run abbreviated Gate 1 (build + lint + security-scan + addon tests)
    #    — no soak, no Gate 2 staging deploy
    # 5. Verify target_sha is HEAD of hotfix_branch

  approval:
    needs: [preflight]
    environment: prod-hotfix   # N=2 prod-deployers required

  deploy:
    needs: [approval]
    # Rolling deploy to BOTH platforms (no choice; full deploy)

  parity-gate:
    needs: [deploy]

  full-wave-deploy:
    needs: [parity-gate]
    # wave=all (no canary stage for hotfix)

  smoke:
    needs: [full-wave-deploy]

  spec-generator-file-retro:
    needs: [smoke]
    # Trigger Spec Generator to draft a retro fix-brief.
    # File issue: 'Retro fix-brief required for hotfix <sha>' with 48h deadline.

  audit:
    if: always()
    needs: [smoke]
    # saas.audit.event: actor, sha, severity, reason

  notify:
    if: always()
    # Slack + page on-call + email prod-deployers
```

### Retro fix-brief enforcement

A separate cron `hotfix-retro-brief-check.yml`:

```
daily:
  for hotfix in audit_events where event='hotfix' and age < 7d:
      if not exists corresponding fix-brief PR:
          if hotfix.age > 48h:
              auto-create issue 'Hotfix <sha> missing retro fix-brief'
              page security-leads
          if hotfix.age > 7d AND no fix-brief AND no revert:
              auto-create issue 'Hotfix <sha> at 7d without retro — propose revert'
              page security-leads + prod-deployers
```

---

## 6. Tenancy impact

The whole spec is about tenancy. Specifically:

- Per-tenant migration jobs are isolated; failure of one tenant doesn't block the wave.
- Per-tenant maintenance windows respected.
- Feature flag flips are per-tenant, scoped to the wave's tenant list.
- Cross-platform parity guarantee preserved.

---

## 7. Data model interactions

Tables read/written:

- `saas.tenant` (existing, extended by main plan §3.3 with `pool_id`, `wave`, `last_migrated_sha`)
- `saas.tenant.migration.job` (existing, defined in main plan §3.3)
- `saas.audit.event` (existing per observability spec)
- `saas.feature.flag` (assumed; if not present, add via separate spec)

---

## 8. Security model

- All three workflows require GitHub Environment-level reviewer approval.
- N=1 for normal canary/w1; N=2 for w2, hotfix, rollback.
- Paste-back confirmation for rollback and hotfix.
- Service-account PATs scoped per platform.
- Every action audited; audit log is append-only with S3 Object Lock.
- AGENTS_ENABLED kill switch doesn't disable these workflows — humans always need to be able to deploy.

---

## 9. Test plan

### Workflow validation
- Lint workflows with `actionlint`.
- Dry-run promote on staging → simulates the full path.

### Integration
- End-to-end promote of a test SHA to canary on a test-tenant pool → tenant.last_migrated_sha updated; smoke passes.
- Rollback of that same SHA → tenant reverts.
- Hotfix flow on a planted fake-critical → full pipeline runs in test env.

### Adversarial
- Wrong paste-back text → workflow refuses.
- Skip soak time → preflight refuses.
- Tenant migration fails → other tenants in wave proceed; alert fires.
- Rollback to non-existent SHA → preflight refuses.

---

## 10. Rollout plan

Phase 3 of the v7 master roadmap (weeks 4–5). Sub-phases:

- **3a (week 4):** `promote-to-prod.yml` happy path on a test-tenant pool.
- **3b (week 4):** `rollback-prod.yml` and paste-back confirmation.
- **3c (week 5):** `hotfix-prod.yml` + retro brief enforcement cron.
- **3d (week 5):** Wire to real prod pool with first canary tenants.

---

## 11. Observability

- Per-promote dashboard: tenants migrated, success rate, duration, cost.
- Per-rollback dashboard: trigger reason, tenants affected, data-restore opt-in rate.
- Per-hotfix dashboard: time-to-deploy, retro-brief filed (yes/no), 48h compliance.

Alerts:
- Migration failure for any tenant → page on-call.
- Parity gate failed → page on-call.
- Hotfix at 36h without retro brief → Slack warn.
- Hotfix at 48h without retro brief → page security-leads.
- Rollback without paste-back match (attempted bypass) → security alert.

---

## 12. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Migration fails for one tenant | Job-level error logged | Other tenants proceed; on-call investigates; tenant.wave='paused' until fixed |
| Parity gate red | Workflow fail | Roll back the platform that succeeded; investigate the other |
| Paste-back wrong | Preflight fail | Operator re-runs with correct text |
| Soak time not elapsed | Preflight fail | Wait, or override via `risk:low` label downgrade |
| Hotfix lacks retro brief at 48h | Cron alarm | Spec Generator auto-files; if not filed at 7d, revert proposed |
| Approval auto-granted by mistake | (Hard to misconfigure with Environments) | Audit log review; tighten environment rules |
| Concurrent promote attempts | Workflow concurrency: group ensures serialization | Second attempt queues or fails fast |

---

## 13. Open questions

1. Should we add a "weekly rollback rehearsal" cron that runs `dry_run=true` against the agentlab tenant pool? Suggested yes — keeps the path warm.
2. For w2 promotes, is N=2 too strict? Could change to "N=1 if w1 has been live ≥ 48h with no incidents."
3. Should hotfix automatically open a security-leads-only PR for the retro fix-brief, instead of waiting on the operator?
4. The migration job uses Postgres for queue state. Should it be in Redis (faster, easier visibility) instead?
