# migration-dry-run-staging — keepalives + retry on the agentlab pg_dump

**Date:** 2026-05-29
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** #142 (verification blocker)
**Severity:** medium

---

## 1. Symptom

`migration-dry-run-staging` repeatedly fails at the **Pick representative
tenant + pg_dump** step (exit 1) before it can reach `Run odoo -u all`:

```
pg_dump: error: query failed: server closed the connection unexpectedly
pg_dump: detail: Query was: COPY public.res_users_deletion (...) TO stdout;
```

## 2. Repro

1. Trigger `migration-dry-run-staging` (e.g. `-f tenant=acmesas2`).
2. The job opens a `flyctl proxy` to the agentlab Postgres and runs
   `pg_dump` of the tenant over it.
3. Mid-COPY (~30s in) the proxy/connection drops and `pg_dump` aborts; the
   step has no retry, so the whole job fails.

**Reproduced on:** runs `26622043977` (ECONNRESET on flyctl install) and
`26622532904` (pg_dump "server closed the connection unexpectedly").

## 3. Affected tenants & severity

- **Tenants impacted:** none (CI dry-run).
- **Severity:** medium — the migration safety-net job is flaky and can't
  reliably reach `odoo -u all`, which currently blocks the #142
  verification (does masked data survive `-u all`).

## 4. Root cause

The dump streams over a `flyctl proxy` tunnel to the agentlab Postgres,
which drops long-lived connections (the same instability the masker hit as
"connection already closed"). The masker got TCP keepalives + a per-DB
retry in #143, but `migration-dry-run-staging.yml`'s own `pg_dump`
connects to the same proxy with **no keepalives and no retry**, so a
transient drop kills the job.

## 5. Proposed fix

`.github/workflows/migration-dry-run-staging.yml`, the pg_dump invocation:

- Pass libpq **TCP keepalives** via a conninfo string
  (`dbname=$tenant keepalives=1 keepalives_idle=30 keepalives_interval=10
  keepalives_count=5`). Host/user/password still come from the `PG*` env
  vars, so **no secret lands in argv** (preserving the existing posture).
- **Retry** the dump up to 3× on a transient failure, with backoff.

Mirrors the #143 resilience already applied to the masker.

## 6. Regression test

CI is the test: re-running the dry-run survives transient proxy drops and
reaches `Run odoo -u all` (which is the #142 question). No unit test —
this is a workflow shell change; validated by the run itself.

## 7. Rollout

- Severity = medium → fix now (this PR).
- No feature flag — CI workflow change only.
- Note: only the `pg_dump` is hardened here; the optional `psql`
  tenant-pick probe (skipped when a tenant override is passed) still uses
  the bare connection — it's a single fast query, far less drop-prone, and
  left as-is to keep the change focused.
- Verification caveat: can't be exercised from the automation sandbox
  (no Fly); proven by the next `migration-dry-run-staging` run.
