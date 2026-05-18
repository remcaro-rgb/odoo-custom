# Per-Tenant Migration Queue — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** the `saas.tenant.migration.job` model + worker that runs `odoo -u all` per tenant DB during prod promotion. Failures isolate to one tenant; the wave keeps going.

---

## 1. Goal

Promote-to-prod (per the promote-to-prod spec) needs to run schema/data migrations on every tenant in the target wave. A naive `for tenant in wave: odoo -u all -d <tenant>` has two problems:

1. **One slow tenant blocks the wave.** A 50 GB tenant taking 4 hours stops everyone else.
2. **One failure blocks the wave.** A bad migration on one tenant means we either retry forever or stop the whole rollout.

The queue solves both: tenants are migrated independently, failures isolate, and the runner respects per-tenant maintenance windows and size buckets.

---

## 2. Non-goals

- Cross-platform parallelism. One platform (Railway/Fly) is enough at our scale.
- Automated rollback per tenant when a migration fails. Pausing the tenant (`wave='paused'`) is the recovery step; rollback is a separate workflow.
- Long-running data migrations (hours). Those should be split into smaller backfills via cron; this queue handles minutes-scale operations.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────┐
│ promote-to-prod workflow                         │
│   │                                              │
│   │ enqueues migration jobs                      │
│   ▼                                              │
│ ┌────────────────────────────────────────────┐   │
│ │ saas.tenant.migration.job table            │   │
│ │   (in control-plane DB)                    │   │
│ │                                            │   │
│ │   id, tenant_id, target_sha, status,       │   │
│ │   started_at, finished_at, log_url,        │   │
│ │   error_excerpt, snapshot_id,              │   │
│ │   timeout_minutes (default 30)             │   │
│ └────────────────────────────────────────────┘   │
│   │                                              │
│   │ workers pull and execute                     │
│   ▼                                              │
│ ┌────────────────────────────────────────────┐   │
│ │ Migration runners (concurrent, capped)     │   │
│ │   - one per Fly/Railway worker machine     │   │
│ │   - takes a job, runs `odoo -u all -d ...` │   │
│ │   - respects tenant.maintenance_window     │   │
│ │   - respects size bucket (small first)     │   │
│ │   - takes pre-migration snapshot           │   │
│ │   - updates tenant.last_migrated_sha       │   │
│ └────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

---

## 4. Tenancy impact

This IS the tenancy machinery. Specifically:

- Each job is bounded to one tenant DB. A job's runner has read/write access only to its own tenant + the control-plane row.
- The `saas.tenant.maintenance_window` field per tenant is respected (cron-expression style; default 02:00-05:00 in tenant TZ).
- Failures are isolated; the wave's other tenants proceed.

---

## 5. Data model

```python
class TenantMigrationJob(models.Model):
    _name = 'saas.tenant.migration.job'
    _description = 'Per-tenant migration job (runs odoo -u all)'

    tenant_id          = fields.Many2one('saas.tenant', required=True, index=True)
    target_sha         = fields.Char(required=True, index=True)
    status             = fields.Selection([
        ('queued',    'Queued'),
        ('blocked',   'Blocked — outside maintenance window'),
        ('running',   'Running'),
        ('done',      'Done'),
        ('failed',    'Failed'),
        ('skipped',   'Skipped — already at target SHA'),
        ('timedout',  'Timed out')], default='queued', index=True)
    timeout_minutes    = fields.Integer(default=30)
    started_at         = fields.Datetime()
    finished_at        = fields.Datetime()
    duration_seconds   = fields.Integer(compute='_compute_duration')
    snapshot_id        = fields.Char(help='pgbackrest snapshot taken before migration')
    log_url            = fields.Char(help='link to runner log in artifact store')
    error_excerpt      = fields.Text()
    retry_count        = fields.Integer(default=0)
    enqueued_by        = fields.Char(help='workflow run id that enqueued')
```

Plus on `saas.tenant`:

```python
class SaasTenant(models.Model):
    # ... existing ...
    size_bucket         = fields.Selection([
        ('xs','XS <1GB'),('s','S 1-5GB'),('m','M 5-20GB'),
        ('l','L 20-50GB'),('xl','XL >50GB')], compute='_compute_size_bucket', store=True)
    maintenance_window  = fields.Char(default='0 2 * * *',  # cron, default 02:00 daily
                                       help='When migrations may start (tenant TZ)')
    tz                  = fields.Char(default='America/Bogota')
    last_migrated_sha   = fields.Char(index=True)
```

---

## 6. Job lifecycle

```
[enqueued by promote-to-prod]
  │
  ▼
queued
  │  runner picks up
  ▼
in maintenance window? ──no──> blocked  (waits; runner re-evaluates each cycle)
  │ yes
  ▼
take pgbackrest snapshot (≤ 4h old? skip; else take fresh)
  │
  ▼
running
  │  odoo -u all -d <tenant>
  │  with timeout
  │
  ▼
┌─ exit 0 ─────────────────────────┐
│ tenant.last_migrated_sha = target │
│ status = done                     │
│ audit event written               │
└───────────────────────────────────┘
       │
┌─ exit !=0 ───────────────────────┐
│ status = failed                   │
│ error_excerpt = last 50 lines     │
│ on-call paged                     │
│ tenant.wave = 'paused' (auto)     │
└───────────────────────────────────┘
       │
┌─ timeout reached ────────────────┐
│ status = timedout                 │
│ kill the odoo process             │
│ tenant.wave = 'paused' (auto)     │
│ on-call paged                     │
└───────────────────────────────────┘
```

---

## 7. Runner

The runner is a small Python loop (could be a separate Fly machine or a GHA matrix job):

```python
def run_migration_loop(concurrency: int = 3):
    while True:
        with db.transaction():
            # Pick the next job: smallest tenants first, in maintenance window
            job = db.execute("""
                SELECT j.* FROM saas.tenant.migration.job j
                JOIN saas.tenant t ON j.tenant_id = t.id
                WHERE j.status IN ('queued', 'blocked')
                  AND in_maintenance_window(t.maintenance_window, t.tz)
                ORDER BY t.size_bucket ASC, j.id ASC
                LIMIT 1 FOR UPDATE SKIP LOCKED;
            """).fetchone()

            if job is None:
                time.sleep(10)
                continue

            if not in_maintenance_window(job.tenant.maintenance_window, job.tenant.tz):
                update_status(job, 'blocked')
                continue

            update_status(job, 'running')

        # Outside the txn, run odoo
        snapshot_id = take_snapshot_if_stale(job.tenant_id)
        update_field(job, 'snapshot_id', snapshot_id)

        try:
            result = subprocess.run(
                ['odoo', '-u', 'all', '-d', job.tenant.dbname,
                 '--stop-after-init', '--no-http'],
                timeout=job.timeout_minutes * 60,
                capture_output=True,
            )
            if result.returncode == 0:
                update_field(job.tenant, 'last_migrated_sha', job.target_sha)
                update_status(job, 'done')
                audit_event('tenant-migrated', tenant=job.tenant_id, sha=job.target_sha)
            else:
                update_status(job, 'failed', error=result.stderr[-50_000:])
                pause_tenant(job.tenant_id, reason='migration-failed')
                audit_event('tenant-migration-failed', tenant=job.tenant_id, sha=job.target_sha)
                page_on_call(...)
        except subprocess.TimeoutExpired:
            update_status(job, 'timedout')
            pause_tenant(job.tenant_id, reason='migration-timeout')
            audit_event('tenant-migration-timedout', tenant=job.tenant_id, sha=job.target_sha)
            page_on_call(...)
```

Concurrency: default 3 (configurable). Higher than this risks overwhelming the Postgres host.

### Idempotency

Re-running a job with the same `target_sha` for a tenant already at that SHA → `status = skipped`, no-op. Enables safe retry on transient failures.

---

## 8. Security model

- Runner runs with a dedicated Postgres role (`migration_runner`) that has `CREATE`, `ALTER`, `INSERT`, `UPDATE` on tenant DBs but not on the control-plane DB except for the queue table.
- Snapshot taking uses pgbackrest service-account credentials (existing).
- Audit events for every status transition.

---

## 9. Test plan

### Unit
- `in_maintenance_window()` over 30 fixture (cron, time, tz) tuples.
- `pick_next_job()` honours size ordering + maintenance window.
- `update_status()` is idempotent under retry.

### Integration
- Enqueue 5 jobs of varied sizes against an agentlab tenant pool → all run in size order; all succeed.
- Plant a bad migration → that tenant's job fails; tenant is paused; others succeed.
- Plant a slow migration → exceeds timeout; tenant paused.
- Outside-window job stays `blocked`; transitions to `queued` when window opens.

### Adversarial
- Tenant tries to be in two waves simultaneously → fail-fast at job enqueue.
- Migration runner crashes mid-job → on restart, the `SKIP LOCKED` row stays locked until the crashed transaction times out; another runner picks it up; idempotency check prevents double-run.

---

## 10. Rollout plan

Phase 4 of v7 master roadmap (week 6). Sub-phases:

- **4a:** `saas.tenant.migration.job` model + UI in Odoo control-plane addon.
- **4b:** Runner implementation + smoke test against agentlab.
- **4c:** Wire to `promote-to-prod.yml` (replace inline migration loop).
- **4d:** Size bucket auto-population cron + maintenance-window cron parser.

### Canary
1. Dry-run on agentlab tenant pool only.
2. Live on canary wave for 2 weeks.
3. All waves.

---

## 11. Observability

- Per-tenant migration job dashboard panels:
  - Jobs by status (queued / running / done / failed / timedout)
  - Mean / p95 duration per size bucket
  - Failure rate by wave
  - Pending job age (queue depth + how long they've been blocked)

Alerts (per observability spec §8):
- Any `failed` or `timedout` status → page on-call.
- Pending job age > 24h → warn.
- Queue depth > 100 → warn.

---

## 12. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Postgres host overwhelmed | Postgres connection saturation | Reduce concurrency; queue absorbs |
| Tenant DB corrupted mid-migration | Migration fails | Restore from `snapshot_id`; humans investigate |
| Maintenance window cron malformed | Parse error at enqueue | Job marked `blocked` with error; manual fix |
| Runner crashes | Job stays `running` past expected duration | Heartbeat detection: stale `running` > 2× timeout → reset to `queued` |
| Two runners pick same job (race) | `FOR UPDATE SKIP LOCKED` prevents | n/a |
| Tenant size bucket stale | Wrong ordering | Daily refresh cron; not a correctness issue, just a perf one |
| Network partition between runner and Postgres | Heartbeat detection | Runner crash recovery |

---

## 13. Open questions

1. Postgres for the queue is operationally simple; should we move to Redis for fast polling? Cost: another service to operate.
2. Should `maintenance_window` be a richer expression (e.g. "Tue/Thu 02-05 only")? Current cron syntax handles this but is awkward.
3. Should we cap concurrent migrations per pool (Railway pool vs Fly pool), in addition to the global concurrency cap?
4. Auto-resume from `paused` after a tenant's manual investigation? Or always require human re-enable?
