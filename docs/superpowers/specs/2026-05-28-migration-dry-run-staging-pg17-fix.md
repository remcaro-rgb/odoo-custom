# migration-dry-run-staging — align Postgres major with agentlab (17)

**Date:** 2026-05-28
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** #137
**Severity:** high

---

## 1. Symptom

`migration-dry-run-staging.yml` fails on **every push to `main`**. The
populated-data migration dry-run — the safety net that catches migrations
which misbehave on real-shaped data — has been red and therefore offline.

## 2. Repro

1. Push anything to `main` (the workflow's only push trigger).
2. Watch **Migration dry-run (-u all on staging snapshot) → Pick
   representative tenant + pg_dump**.
3. It aborts:

```
pg_dump: error: aborting because of server version mismatch
pg_dump: detail: server version: 17.7 (Ubuntu 17.7-3.pgdg24.04+1); pg_dump version: 16.14 (Ubuntu 16.14-1.pgdg24.04+1)
##[error]Process completed with exit code 1.
```

**Reproduced on:** failed run `26530009233` (2026-05-27) and every push to
`main` since the agentlab DB was upgraded to 17.

## 3. Affected tenants & severity

- **Tenants impacted:** none directly (CI safety gate, post-merge).
- **Severity:** high — with the dry-run red, a migration that misbehaves on
  populated data would reach prod undetected. It is **not** a required PR
  status check (push-to-main only), so it does not block merges, but the
  safety net must be restored.

## 4. Root cause

The agentlab source Postgres (snapshot source, reached via `flyctl proxy`)
was upgraded to **17.7**. The `ubuntu-latest` runner ships `pg_dump`
**16.14**. `pg_dump` refuses to dump from a server whose major version is
newer than its own, so the dump in the tenant-pick step aborts. Everything
before that point is healthy (preflight passes, `flyctl proxy` connects).

The repeating `FATAL: database "odoo" does not exist` lines in the log are
a **red herring** — they are the job-local Postgres service container's
healthcheck (`pg_isready -U odoo` with no `-d`, pinging the nonexistent
`odoo` DB; the service DB is `postgres`). They are benign and unrelated to
the failure; they merely resembled the PR #123 init-timing race.

This is **flyctl/runner version drift surfacing a major-version skew**, a
real regression — not a flake.

## 5. Proposed fix

`.github/workflows/migration-dry-run-staging.yml`:

1. **Install the v17 client on the runner** and put it ahead of v16 on
   `PATH`, so `pg_dump`/`psql` are v17 and can dump the 17.7 server:

   ```yaml
   - name: Install PostgreSQL 17 client (match agentlab server major)
     if: steps.preflight.outputs.skip != 'true'
     run: |
       set -euo pipefail
       sudo apt-get update
       sudo apt-get install -y postgresql-common
       sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
       sudo apt-get install -y postgresql-client-17
       echo "/usr/lib/postgresql/17/bin" >> "$GITHUB_PATH"
       /usr/lib/postgresql/17/bin/pg_dump --version
   ```

2. **Bump the job-local restore Postgres** to match the dump's major (a v17
   dump restored into a v16 server can fail), and keep the dry-run
   prod-shaped:

   ```yaml
   services:
     postgres:
       image: postgres:17-alpine   # was postgres:16-alpine
   ```

3. **(Hygiene)** Silence the misleading healthcheck noise:

   ```yaml
   --health-cmd="pg_isready -U odoo -d postgres"   # was: -U odoo
   ```

## 6. Regression test

CI itself is the test:

- After merge, the next push to `main` runs **Migration dry-run** and the
  **Pick representative tenant + pg_dump** step succeeds (`pg_dump`
  reports v17, no version-mismatch abort).
- The `database "odoo" does not exist` healthcheck lines no longer appear.

## 7. Rollout

- Severity = high → fix now (this PR).
- No feature flag — CI workflow change only.
- **Verification caveat:** this could not be end-to-end verified from the
  automation sandbox (no Fly token, outbound API blocked). The real proof
  is the post-merge run on `main`; it also depends on agentlab having a
  tenant DB available (otherwise the job skips gracefully). If a future
  agentlab upgrade moves to PG 18+, bump the client install + service image
  in lockstep.
