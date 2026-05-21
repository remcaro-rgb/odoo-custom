# `tenant_migration_jobs` — Phase 4 runbook

## What it is

A FIFO queue (Postgres table) in the control-plane DB that holds one row
per (tenant, target_sha) pair. The `promote-to-prod` workflow enqueues
rows; per-platform runners (one per Fly/Railway worker machine) consume
them, run `odoo -u all -d <db_name>` against the matching tenant DB,
update `tenants.last_migrated_sha`, and write an audit event.

Schema: owned by the **control-plane repo's Drizzle schema**
(`packages/db/src/schema.ts` → `tenants`, `tenant_migration_jobs`),
migration `0009_tenant_migration_queue.sql`.

Spec: [`docs/superpowers/specs/2026-05-16-tenant-migration-queue-design.md`](../../docs/superpowers/specs/2026-05-16-tenant-migration-queue-design.md).

---

## What's shipped vs. deferred

### Shipped

- **Drizzle schema** in the control-plane repo: the Phase-4 columns on
  `tenants` (`wave`, `last_migrated_sha`, `size_bucket`,
  `maintenance_window`, `tz`) and the `tenant_migration_jobs` table.
- **Drizzle migration** `0009_tenant_migration_queue.sql`.
- Indices for the runner's hot paths (status lookup, heartbeat sweep).
- This runbook.

> **Schema ownership note.** An earlier draft kept this DDL as a raw SQL
> file in the data-plane repo (`infra/sql/saas-tenant-migration-schema.sql`),
> which invented a standalone `saas.tenant` table. That duplicated the
> canonical `public.tenants` Drizzle table and was retired — the queue
> now attaches directly to `tenants`.

### Deferred (separate sessions)

- **tRPC endpoints** for the workflow to enqueue jobs and for runners
  to claim them (if the runner ends up going through the API rather
  than direct psql).
- **Daily size_bucket cron** — measures each tenant DB with
  `pg_database_size()` from the data-plane side (control-plane role lacks
  `USAGE` on tenant DBs) and UPDATEs `tenants.size_bucket` via the
  control-plane API.
- **The runner itself** — a Python daemon or GHA matrix job that pulls
  jobs and runs `odoo -u all` with a timeout. Materially blocked on
  agentlab (Phase 5b) because we want to test against masked production
  data before pointing at real tenants.

---

## First-time setup

The schema is applied as part of the control-plane repo's normal
Drizzle migration flow:

```bash
# In the Odoo-control-plane repo, with DATABASE_URL set:
pnpm --filter db exec drizzle-kit migrate
```

Verify:

```sql
\d+ tenants
\d+ tenant_migration_jobs
```

---

## How a promote-to-prod run uses this

`promote-to-prod.yml` enqueues one job per wave tenant that is not yet
at the target SHA:

```yaml
- name: Enqueue per-tenant migration jobs
  env:
    PG_DSN: ${{ secrets.CONTROL_PLANE_PG_DSN }}
  run: |
    psql "$PG_DSN" -c "
      INSERT INTO tenant_migration_jobs (tenant_id, target_sha, status, enqueued_by)
      SELECT id, '$SHA', 'queued', 'promote-to-prod-$RUN_ID'
      FROM tenants WHERE slug = '$tenant'
    "
```

The wave/SHA filtering happens in the workflow's preflight step
(`last_migrated_sha IS DISTINCT FROM target AND state = 'active'`).

## How a runner uses this

```python
# Claim one job
job = db.execute("""
    UPDATE tenant_migration_jobs
    SET status = 'running',
        started_at = now(),
        heartbeat_at = now()
    WHERE id = (
        SELECT id FROM tenant_migration_jobs
        WHERE status IN ('queued', 'blocked')
        ORDER BY enqueued_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *
""").fetchone()

if job is None:
    sleep(15); continue

# Check maintenance window. If outside → set 'blocked' and release.
if not _in_window(job.tenant.maintenance_window, job.tenant.tz):
    db.execute("UPDATE tenant_migration_jobs SET status='blocked' WHERE id=%s", job.id)
    continue

# Take pgbackrest snapshot (skip if one <= 4h old exists).
snapshot_id = ensure_snapshot(job.tenant.db_name, max_age_hours=4)
db.execute("UPDATE tenant_migration_jobs SET snapshot_id=%s WHERE id=%s", snapshot_id, job.id)

# Run migration with timeout.
try:
    subprocess.run(
        ["odoo", "-u", "all", "-d", job.tenant.db_name, "--stop-after-init"],
        timeout=job.timeout_minutes * 60,
        check=True,
    )
    db.execute("""
        UPDATE tenant_migration_jobs
        SET status='done', finished_at=now() WHERE id=%s
    """, job.id)
    db.execute("""
        UPDATE tenants
        SET last_migrated_sha=%s, updated_at=now() WHERE id=%s
    """, job.target_sha, job.tenant_id)
    audit('system', 'runner', 'tenant-migrated',
          target_kind='tenant', target_id=job.tenant.slug, sha=job.target_sha)
except subprocess.TimeoutExpired:
    db.execute("""
        UPDATE tenant_migration_jobs
        SET status='timedout', finished_at=now() WHERE id=%s
    """, job.id)
    db.execute("UPDATE tenants SET wave='paused' WHERE id=%s", job.tenant_id)
    page_oncall(job)
except subprocess.CalledProcessError as e:
    db.execute("""
        UPDATE tenant_migration_jobs
        SET status='failed', finished_at=now(),
            error_excerpt=%s WHERE id=%s
    """, e.stderr[-50000:], job.id)
    db.execute("UPDATE tenants SET wave='paused' WHERE id=%s", job.tenant_id)
    page_oncall(job)
```

Heartbeat: a background thread updates `heartbeat_at = now()` every 60s
while the job is `running`. A sweeper (cron, every 5 min) re-queues
running jobs whose heartbeat is older than `2 * timeout_minutes`:

```sql
UPDATE tenant_migration_jobs
SET status='queued',
    retry_count = retry_count + 1,
    heartbeat_at = NULL,
    started_at = NULL,
    error_excerpt = 'stale heartbeat — runner crashed'
WHERE status='running'
  AND heartbeat_at < now() - make_interval(mins => 2 * timeout_minutes);
```

---

## Common queries

```sql
-- Queue depth right now (broken down by status)
SELECT status, count(*) AS n FROM tenant_migration_jobs
WHERE finished_at IS NULL
GROUP BY status ORDER BY status;

-- Failed/timedout jobs in the last 24h with their tenant
SELECT j.id, t.slug, j.status, j.target_sha, j.error_excerpt
FROM tenant_migration_jobs j JOIN tenants t ON t.id = j.tenant_id
WHERE j.finished_at > now() - interval '24 hours'
  AND j.status IN ('failed','timedout')
ORDER BY j.finished_at DESC;

-- p95 duration per size bucket (last 30d, completed only)
SELECT t.size_bucket,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (j.finished_at - j.started_at))) AS p95_seconds,
       count(*) AS n
FROM tenant_migration_jobs j JOIN tenants t ON t.id = j.tenant_id
WHERE j.status='done' AND j.finished_at > now() - interval '30 days'
GROUP BY t.size_bucket ORDER BY 2 DESC;

-- Tenants currently paused (excluded from waves until manually un-paused)
SELECT slug, region, last_migrated_sha
FROM tenants WHERE wave='paused' ORDER BY updated_at DESC;
```

---

## Manual interventions

### Un-pause a tenant after operator review

```sql
UPDATE tenants SET wave = 'canary', updated_at = now()
WHERE slug = '<tenant>' AND wave = 'paused';
```

Then enqueue a retry job manually:

```sql
INSERT INTO tenant_migration_jobs (tenant_id, target_sha, enqueued_by)
SELECT id, '<sha>', 'manual-retry-<your-name>' FROM tenants WHERE slug='<tenant>';
```

### Force-skip a stuck job

```sql
UPDATE tenant_migration_jobs
SET status='skipped', finished_at=now(),
    error_excerpt='manually skipped by <operator>: <reason>'
WHERE id='<job_id>' AND status IN ('queued','blocked','running');
```

If `status` was `running`, the runner's next heartbeat will see the row
moved to `skipped` and abort the `odoo -u all` subprocess.

---

## Related work

- Schema: control-plane repo `packages/db/src/schema.ts`
  (`tenants`, `tenant_migration_jobs`), migration
  `0009_tenant_migration_queue.sql`.
- Spec: [`docs/superpowers/specs/2026-05-16-tenant-migration-queue-design.md`](../../docs/superpowers/specs/2026-05-16-tenant-migration-queue-design.md)
- Audit log every migration writes to: [`saas_audit.event`](./saas-audit-event.md)
- Phase 3 consumer: `promote-to-prod.yml` enqueue step
- Phase 5b dependency: agentlab is the safe test bed for the runner
