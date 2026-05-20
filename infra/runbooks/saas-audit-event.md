# `saas_audit.event` — operational runbook

## What it is

A single append-only Postgres table that captures every production action
worth replaying after an incident: promotes, rollbacks, preview-env
lifecycle changes, agentlab restores, agent merges. Source of truth for
"who deployed what to whom when, and why" (master plan §14).

DDL: [`infra/sql/saas-audit-event-schema.sql`](../sql/saas-audit-event-schema.sql).

Location: **control-plane Postgres**, reached via the
`CONTROL_PLANE_PG_DSN` repo secret. Not in any tenant DB — this is the
operator's record, not tenant data.

---

## First-time setup

```bash
# As an admin user with CREATE SCHEMA privilege on the control-plane DB.
psql "$CONTROL_PLANE_PG_DSN" -f infra/sql/saas-audit-event-schema.sql
```

The script is idempotent (`CREATE … IF NOT EXISTS`, `DROP TRIGGER … IF
EXISTS` before re-creating); safe to re-apply.

Verify:

```sql
\d+ saas_audit.event
SELECT triggers.trigger_name, action_timing, event_manipulation
FROM information_schema.triggers WHERE event_object_schema = 'saas_audit';
```

Expect: the table with the columns from the spec and two triggers
(`saas_audit_event_no_update`, `saas_audit_event_no_delete`).

---

## Writing events

### From a workflow

The two existing emitters:

| Workflow | Action | Actor |
|---|---|---|
| [`preview-cleanup.yml`](../../.github/workflows/preview-cleanup.yml) | `preview-env-destroyed` | `system` / `preview-cleanup` |
| [`rollback-prod.yml`](../../.github/workflows/rollback-prod.yml) | `rollback-prod` | `human` / `${{ github.actor }}` |

Future emitters (Phase 3+) should follow the same pattern:

```yaml
- name: Audit
  if: always()
  env:
    PG_DSN: ${{ secrets.CONTROL_PLANE_PG_DSN }}
  run: |
    psql "$PG_DSN" -c "
      INSERT INTO saas_audit.event
        (actor_kind, actor_name, action, target_kind, target_id, sha, wave, reason, payload)
      VALUES
        ('human', '${{ github.actor }}', 'promote-to-prod', 'wave', '${{ inputs.wave }}',
         '${{ inputs.target_sha }}', '${{ inputs.wave }}', NULL,
         '{\"dry_run\": ${{ inputs.dry_run }}}'::jsonb)
    "
```

Quote `payload` as JSON-encoded text and cast to `jsonb` to defend against
the shell-quoting trap: always pass through `jq -Rs .` if the payload
includes file contents.

### From an Odoo addon

There is no Odoo model for `saas_audit.event` in this repo because the
table lives outside any Odoo instance. If an Odoo addon needs to emit
audit events, route through the control-plane HTTP API (Phase 5+) rather
than writing to a foreign DB from Odoo workers.

### Severity & sampling

Audit events are not subject to sampling. Every emit must reach the
table — failures should fail the workflow, NOT swallow with `|| true`.

There is one existing exception: `preview-cleanup.yml`'s audit step uses
`|| true` because the workflow predates the table being created in the
control-plane DB. Remove the `|| true` once the DDL is applied (track as
a Phase 3 cleanup commit).

---

## Common queries

```sql
-- All rollbacks in the last 7 days
SELECT ts, actor_name, wave, sha, reason
FROM saas_audit.event
WHERE action = 'rollback-prod' AND ts > now() - interval '7 days'
ORDER BY ts DESC;

-- Every action by a specific human
SELECT ts, action, target_kind, target_id, wave, sha
FROM saas_audit.event
WHERE actor_kind = 'human' AND actor_name = 'manu'
ORDER BY ts DESC LIMIT 50;

-- Preview env churn this week
SELECT date_trunc('day', ts) AS day, count(*) AS destroyed
FROM saas_audit.event
WHERE action = 'preview-env-destroyed'
  AND ts > now() - interval '7 days'
GROUP BY 1 ORDER BY 1;

-- All actions affecting a specific SHA
SELECT ts, actor_kind, actor_name, action, wave, reason
FROM saas_audit.event
WHERE sha = 'c68c360d963706c0b170b85dbcbed19c8b0bb49e'
ORDER BY ts;
```

---

## What CAN'T happen (by construction)

- **UPDATE / DELETE** rows: the triggers raise `integrity_constraint_violation`.
  Even the table owner gets the error.
- **TRUNCATE**: only the table owner can issue it; doing so produces a
  loud DDL trace in `pg_stat_activity`. Compliance retention is the
  nightly S3 export with Object Lock (cf. observability spec §7) — even
  if someone truncates, prior day's snapshot survives.
- **DROP**: same — admin operation, visible.

---

## Retention

Live table grows linearly with operator activity (~50–200 rows/day at
current scale). Plan §11 §7 specifies nightly export to S3 with
Object Lock (999-year retention) and 90-day on-line retention; the
export job is Phase 5 work and not yet shipped. Until then, manual
backups via `pg_dump --table=saas_audit.event` are sufficient.

---

## Incident-response order of operations

1. `psql "$CONTROL_PLANE_PG_DSN" -c "SELECT now()"` — confirm connectivity.
2. Run one of the "Common queries" above tied to the suspected window.
3. Cross-reference `request_id` against Better Stack to pull matching
   log lines (Phase 5).
4. If a row is suspect (e.g. `actor_name` doesn't match expected),
   correlate `sha` with `git log` and the GHA run log
   (`gh run list --workflow=<workflow.yml> --branch=<branch>`).

---

## Related work

- DDL: [`infra/sql/saas-audit-event-schema.sql`](../sql/saas-audit-event-schema.sql)
- Spec: [`docs/superpowers/specs/2026-05-16-observability-stack-design.md`](../../docs/superpowers/specs/2026-05-16-observability-stack-design.md) §7
- Master plan: §9 (Observability & audit), §10 (Agent governance)
- Future emitters (Phase 3+): `promote-to-prod.yml`, `hotfix-prod.yml`
- Future emitters (Phase 5): `agentlab-daily-restore.yml`
