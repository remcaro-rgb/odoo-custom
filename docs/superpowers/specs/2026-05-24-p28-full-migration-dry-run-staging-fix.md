# Phase 2 P2.8 full — `migration-dry-run` vs a staging tenant DB snapshot

**Date:** 2026-05-24
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (Phase 2 of `docs/2026-05-15-spec-driven-dev-plan.md` — item P2.8 full variant)
**Linked issue:** N/A — completes Phase 2 P2.8
**Severity:** medium

---

## 1. Symptom

PR #41 shipped the LIGHTWEIGHT P2.8: `migration-dry-run` installs the
changed addons fresh into a CI Postgres and then runs `odoo -u all`
against that just-installed DB. That catches migration script syntax
errors and `_register_hook` / `_init_column` regressions.

It does NOT catch migration regressions that depend on real-shaped
data: a migration script that misbehaves only when a column has
non-trivial existing values, a unique constraint that's fine on an
empty table but fails on a populated one, a `pre-migrate` hook that
reads `ir_model` and the table content interactively.

The roadmap (`docs/2026-05-15-spec-driven-dev-plan.md` §P2.8) calls
for the FULL variant: pull a recent snapshot of a representative
staging tenant from agentlab (which already keeps masked daily
snapshots of every staging tenant), restore into a fresh DB in CI,
and run `odoo -u all` against THAT DB.

## 2. Repro

A migration script that does:

```python
def migrate(cr, version):
    # Set a column to a computed value derived from existing data.
    cr.execute("UPDATE x SET cost_center_id = (SELECT id FROM cost_center WHERE code = ...)")
```

Passes the lightweight P2.8 (no rows in `x` on a fresh install →
nothing to UPDATE), but crashes against a populated tenant where the
subquery returns NULL for some rows that need a NOT NULL constraint.
Only the full variant catches this.

## 3. Affected tenants & severity

- **Tenants impacted:** none directly (CI-only gate), but a regression
  that gets past this is a real tenant-runtime incident at upgrade time.
- **Severity:** medium. Catches a real class of bug that the lightweight
  variant cannot.

## 4. Root cause

Phase 2 roadmap deliverable explicitly identified as deferred from
PR #41. Today's session completes it.

## 5. Proposed fix

New workflow file: `.github/workflows/migration-dry-run-staging.yml`.

### Trigger

- `push` to `main` only — too expensive for every PR (15–25 min).
- `workflow_dispatch` with optional `tenant` input for manual runs.

### Connectivity

Agentlab Postgres lives on Fly's 6PN private network. Access pattern
established by `.github/workflows/agentlab-daily-restore.yml`:

1. `superfly/flyctl-actions/setup-flyctl@master`
2. `flyctl proxy 15432:5432 -a odoo-saas-odoo-agentlab-db &`
3. `pg_dump` from `127.0.0.1:15432` using `AGENTLAB_DSN` rewritten
   via `infra/scripts/dsn_rewrite_host.py`.

Needs `FLY_AGENTLAB_TOKEN` (NOT the shared `FLY_API_TOKEN` — that's
scoped to `odoo-saas-odoo` only and 401s on cross-app GraphQL —
see `.github/SECRETS.md`).

### Snapshot selection

The representative tenant is configurable via repo variable
`P28_REPRESENTATIVE_TENANT` (default: the first tenant returned by
`pg_dump -l` — most-recently-touched).

Note: agentlab snapshots are ALREADY masked by `mask_prod_data.py`
when they enter agentlab. The job inherits that masking; it does not
re-mask. The job MUST NOT pull from staging directly (raw prod-shaped
data); it MUST pull from agentlab.

### Job shape

```yaml
migration-dry-run-staging:
  runs-on: ubuntu-latest
  if: github.event_name != 'pull_request'
  needs: ...  # nothing — fully self-contained
  services:
    postgres: { image: postgres:16-alpine, ... }
  timeout-minutes: 25
  env:
    FLY_API_TOKEN: ${{ secrets.FLY_AGENTLAB_TOKEN }}
    AGENTLAB_DSN: ${{ secrets.AGENTLAB_DSN }}
  steps:
    - actions/checkout
    - superfly/flyctl-actions/setup-flyctl
    - Open flyctl proxy (background)
    - Pull pg_dump of the representative tenant
    - docker build Odoo (cached)
    - psql restore into services Postgres
    - docker run odoo-saas:migrate-staging with UPDATE_MODULES=all
    - Cleanup proxy
```

### Failure modes

- **Missing secret** — job no-op-passes with a clear log line. Pairs
  with the existing `agentlab-daily-restore` job whose secrets become
  visible to this workflow once the org admin enables them.
- **No tenants in agentlab** — same: no-op-pass, log message. First
  successful daily-restore unblocks this job.
- **`odoo -u all` exit code non-zero** — fail the job.

## 6. Regression test

CI itself is the test: the new job appears in the push-to-main check
rollup. First successful run validates against the current agentlab
snapshot.

A separate test PR could intentionally introduce a migration script
that fails on populated data; the job catches it. Out of scope here.

## 7. Rollout

- Severity = medium → ride the next normal wave.
- No feature flag — pure CI addition.
- Triggers on push-to-main only; no PR latency impact.
- Expected outcomes:
  - New `migration-dry-run-staging` job visible on every push to main.
  - First run reads from the most-recent agentlab daily-restore
    snapshot. Subsequent runs always pick up the latest.
  - Phase 2 P2.8 fully complete (10/10 Phase 2 items shipped).
