# moveTier runbook

Operator procedure for migrating a tenant between tiers (shared ↔ exclusive) and platforms (Railway ↔ Fly). Backed by the `moveTier` WDK workflow shipped in Phase 3.

## When to use moveTier

| Scenario | Action |
|---|---|
| Customer signs up for the **exclusive** tier from shared | `moveTier(tenantId, 'exclusive')` |
| Customer downgrades exclusive → shared | `moveTier(tenantId, 'shared')` *(Phase 3.x — reverse path TODO)* |
| Move tenant to different platform (e.g., Railway → Fly for latency) | `moveTier(tenantId, targetTier, targetPlatform: 'fly')` |
| Recover from a noisy-neighbor incident (move tenant off a shared cluster) | `moveTier(tenantId, 'exclusive')` |

**Not for**: routine ops, scaling, DB upgrades, restoring from backup, point-in-time recovery. Those are separate runbooks.

## Pre-flight (one-time setup)

All env vars must exist on the Vercel admin app (production environment). The list is enforced by `prepareTarget`'s `requireEnv()` calls; missing values cause an early `FatalError`.

| Env var | Source | Notes |
|---|---|---|
| `TENANT_POSTGRES_IMAGE` | `ghcr.io/<owner>/odoo-saas-postgres:sha-<7>` | Pin to a specific SHA. Bump after each `ghcr-publish.yml` run. |
| `TENANT_ODOO_IMAGE` | `ghcr.io/<owner>/odoo-saas-odoo:sha-<7>` | Same pinning rule. |
| `TENANT_POSTGRES_PASSWORD` | Strong random (`openssl rand -base64 36 \| tr -d '/+=' \| cut -c1-48`) | Master password for ALL per-tenant exclusive Postgres clusters. **Sensitive**. |
| `ODOO_ADMIN_PASSWORD` | Same strong-random recipe | Master `admin_passwd` for per-tenant exclusive Odoo. **Sensitive**. |
| `FLY_ORG_SLUG` | `personal` (or your Fly org slug) | Found via `flyctl orgs list`. |
| `FLY_API_TOKEN` | `flyctl auth token` output (starts `FlyV1 fm2_…`) | **Sensitive**. Org-scoped works. |
| `FLY_ODOO_APP_NAME` | `odoo-saas-odoo` | The shared Fly Odoo pool. |
| `FLY_POSTGRES_ADMIN_URL` | `postgres://odoo:<pw>@odoo-saas-postgres.internal:5432/postgres` | Used by source-side cluster routing for dumpSource. **Sensitive**. |
| `FLY_TRAEFIK_REDIS_URL` | `redis://odoo-saas-redis.internal:6379` | Internal hostname; only the runner uses it. |
| `RAILWAY_REPO_FULL_NAME` | `GoliattCo/odoo-custom` | GitHub repo for Railway service-create source. |
| `RAILWAY_*` (full set) | See `packages/infra/src/providers/railway.ts` constructor | Required only if doing moveTier targeting Railway. |
| `BACKUP_RUNNER_URL` | `https://odoo-saas-backup-runner.fly.dev` | Must be the **public** URL, not the 6PN internal. |
| `BACKUP_RUNNER_TOKEN` | Strong random, mirrored on the runner's secret | **Sensitive**. |
| `SAAS_PROVISIONING_SECRET` | Pool-wide HMAC secret | Shared with `saas_provisioning_gateway` addon on every Odoo image. **Sensitive**. |

Also on the **backup-runner** Fly app (`flyctl secrets set --app odoo-saas-backup-runner`):

| Runner secret | Value | Purpose |
|---|---|---|
| `BACKUP_RUNNER_TOKEN` | Mirrors Vercel | Bearer auth on `/v1/*` |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` | Shared cluster credentials | Default cluster routing (when request omits `cluster`) |
| `FLY_TRAEFIK_REDIS_URL` | `redis://odoo-saas-redis.internal:6379` | Where admin-ops writes Traefik KV |
| `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | From `Terraform output` for the backup pgBackRest role | S3 access for backup-tenant / restore-tenant |

## Firing the migration

### Option A: `/api/internal/drill` (CRON_SECRET-gated, no Clerk login)

```bash
# From a workstation with the Vercel admin's CRON_SECRET in scope:
vercel env pull /tmp/admin.env --environment=production --yes --cwd ~/Odoo-control-plane/apps/admin
set -a; . /tmp/admin.env; set +a

curl -X POST https://odoo-saas-admin.vercel.app/api/internal/drill \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "moveTier",
    "tenantId": "<uuid>",
    "targetTier": "exclusive"
  }'
```

Returns `{ ok: true, tenantId, targetTier, workflowRunId: "wrun_…" }`.

Optional `"targetPlatform": "fly"|"railway"` — defaults to the tenant's current platform. For cross-platform you must specify.

### Option B: admin tRPC (Clerk-gated, future UI button)

```ts
// Via the admin app's tRPC client after Clerk login:
const result = await trpc.tenants.moveTier.mutate({
  tenantId: '649e…',
  targetTier: 'exclusive',
  targetPlatform: undefined,    // defaults to current
});
```

The UI for this is a future Phase 3 polish item; today the tRPC procedure exists but no button calls it.

## Monitoring progress

The workflow flips `tenants.state` at the lockSource step (~30s after fire) and back to `active` at finalize. Poll:

```bash
curl -sS -X POST https://odoo-saas-admin.vercel.app/api/internal/drill \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"action":"status","tenantId":"<uuid>"}' | jq '.tenant'
```

Expected state progression:
- `state=active tier=shared` → fire moveTier
- `state=migrating_to_exclusive tier=shared` (within 30s — lockSource ran)
- `state=active tier=exclusive` (~60s total for a small tenant)

For deeper visibility, stream Vercel function logs:

```bash
vercel logs https://odoo-saas-admin.vercel.app --cwd ~/Odoo-control-plane/apps/admin
```

Grep for `stepName:`, `errorStack:`, `workflowRunId:`.

## Step pipeline (what's happening at each stage)

| # | Step | Duration | Side effects |
|---|---|---|---|
| 1 | `prepareTarget` | 30-60s | Creates Fly apps + volumes + machines for `odoo-saas-{postgres,odoo}-<slug>`. Allocates public IPs on Odoo app. Inserts new `odoo_instances` row. |
| 2 | `triggerSourceBackupNow` | 10-30s | HMAC POST to source Odoo. Triggers `saas_filestore_backup` addon synchronously. Fresh `filestore_tar` row in `tenant_backups`. |
| 3 | `lockSource` | <1s | UPDATE `tenants.state` ← `migrating_to_exclusive`. |
| 4 | `dumpSource` | 5-60s (tenant size dependent) | Captures source row-count baseline via `/v1/count-rows`. `pg_dump -Fc` → AES-GCM → S3 via `/v1/backup-tenant`. |
| 5 | `restoreToTarget` | 5-60s | `/v1/restore-tenant` with `createDatabase: true`. Runner creates target DB then `pg_restore`. |
| 6 | `rsyncFilestore` | 5-30s | HMAC POST to **target** Odoo's `/saas/internal/filestore-restore` with a 30-min presigned S3 GET URL. Target downloads + AES-GCM decrypts + tar-extracts. |
| 7 | `verifyTarget` | <5s | `/v1/count-rows` against target. Fails if any of `res_users`/`res_partner`/`ir_module_module`/`ir_attachment` deviates >5% from baseline. |
| 8 | `swapTraefik` | <1s | `/v1/admin-ops register-route`. Runner writes Traefik KV on Fly Redis. Wildcard `<slug>.fly.app.goliatt.co` now routes to the exclusive instance. |
| 9 | `smokeTest` | 5-30s | HTTPS GET `/saas/health` on the new public URL. Up to 6 retries × 5s. |
| 10 | `dropSourceAndFinalize` | 1-5s | `/v1/admin-ops drop-db` against the shared cluster (FORCE drops live connections). UPDATE `tenants.{tier,odoo_instance_id,state}`. Cross-platform: `/v1/admin-ops unregister-route` on source platform. Audit log entry. |

Total wall-clock: **~60s** for a fresh tenant, **5-15 min** for a tenant with multi-GB data + filestore.

## Failure modes

The workflow is durable (WDK). On any step failure, WDK retries up to 3 times with exponential backoff. After that, the step bubbles a `FatalError` and the entire workflow aborts. The tenant stays in `state=migrating_to_exclusive` and requires manual intervention.

### Common errors

| Error pattern | Step | Cause | Fix |
|---|---|---|---|
| `RAILWAY_API_TOKEN must be set` | prepareTarget | env var missing on Vercel | set via `vercel env add` |
| `Fly HTTP 404 POST /apps: organization not found` | prepareTarget | wrong `FLY_ORG_SLUG` | should be `personal` for individual accounts |
| `Fly HTTP 401 ... token validation error` | prepareTarget | bad token format (missing `FlyV1 ` prefix) | re-run `flyctl auth token`, paste full output |
| `Region 'us-east-1' cannot host your machine` | prepareTarget volumes.create | tenant.region uses AWS-style name | `UPDATE tenants SET region='iad' WHERE id='<uuid>'` (or `us-east1` for Railway) |
| `initdb: directory exists but is not empty` | postgres init | mount-point has `lost+found` | `PGDATA=/var/lib/postgresql/data/pgdata` (already set; check if envSecrets got truncated) |
| `database "odoo" does not exist` | pgCurrentWalLsn | psql defaulting to db=$PGUSER | already fixed via `-d postgres` (commit `61564fe`); confirm runner deploy is current |
| `ENOTFOUND odoo-saas-postgres.internal` | drop-db / verifyTarget | runner attempting direct connect when it shouldn't | check runner's `PGHOST` env and the cluster routing in the request |
| `Connection refused` to target postgres | restoreToTarget | postgres machine auto-stopped (Fly default) | confirm `autostop=off` in the machine's services config (we set this on creation) |
| `Failed to start postgres ... FATAL: shared memory` | postgres init | machine memory too low | `memoryMb >= 4096` in `provisionTenantPostgres`'s spec |
| `sha256 mismatch` at `verifyTarget` | row-count drift | source DB took writes mid-dump | acceptable up to 5%; if higher, dump+restore lost data — roll back |

### Rollback (workflow died after step 5)

Source DB is intact through step 10. If the workflow died at step 5+ before step 10:

```bash
# 1. Drop the orphan target apps
flyctl apps destroy odoo-saas-postgres-<slug> --yes
flyctl apps destroy odoo-saas-odoo-<slug> --yes

# 2. Roll back the new exclusive odoo_instance row
psql "$DATABASE_URL_UNPOOLED" -c "
  DELETE FROM odoo_instances WHERE id IN (
    SELECT odoo_instance_id FROM tenants WHERE id='<uuid>'
  ) AND tier='exclusive';
"

# 3. Reset tenant state + point back at shared instance
psql "$DATABASE_URL_UNPOOLED" -c "
  UPDATE tenants
  SET state='active', tier='shared',
      odoo_instance_id=(
        SELECT id FROM odoo_instances WHERE platform='<platform>' AND tier='shared' LIMIT 1
      )
  WHERE id='<uuid>';
"
```

After rollback the tenant continues serving from the shared cluster as before. Source DB was never modified by the workflow.

### Rollback (workflow completed but exclusive cluster is unhealthy)

Run `moveTier(tenantId, 'shared')` to reverse the migration. *(Phase 3.x — reverse path is partially implemented; manual procedure for now.)*

## Operational maintenance

### After a successful migration

1. **No action required** if all steps green. The workflow's audit_log entry `tenant.moveTier.success` is the record.
2. Verify the new instance: `curl -I https://<slug>.fly.app.goliatt.co` should return 200 (post-DNS-propagation; allow 30s for Traefik KV cache).
3. Tell the tenant their service is now on the exclusive tier.

### After a successful reverse migration (exclusive → shared)

1. Manual: drop the per-tenant postgres + odoo Fly apps (they're no longer referenced):
   ```bash
   flyctl apps destroy odoo-saas-postgres-<slug> --yes
   flyctl apps destroy odoo-saas-odoo-<slug> --yes
   ```
2. Delete the orphan `odoo_instances` row (still in Neon after the reverse).

## Known limitations (as of v0.4.1)

- **Tenant size**: `pg_dump -Fc` is single-threaded (parallel jobs require `-Fd` directory format). Acceptable for ≤5 GB tenants; switch to `-Fd` in the runner for bigger.
- **Filestore size**: `saas_filestore_backup` uses one-shot AESGCM (cap 256 MiB). Bigger filestores fail at the addon level — switch to streaming AEAD for tenants approaching that.
- **Cross-platform**: code-complete, **not yet drill-validated**. Same-platform Fly → Fly is the only path with a successful end-to-end drill.
- **Railway target**: needs Railway-side Traefik deploy before `swapTraefik` does anything useful. Until then, only Fly tier flips actually flip user-facing traffic.
- **`migrating_to_exclusive` state can stick** if WDK runtime dies mid-workflow without bubbling a FatalError (rare but possible). Manual fix: psql UPDATE state back to `active`.

## Drill log (reference)

- Drill #16.13 — first end-to-end success. 84s for migrate2 on Fly. Two warned-but-tolerated steps (swapTraefik, dropSourceAndFinalize) — fixed in v0.4.
- Drill #17 — fully autonomous, no warnings. 53s for migrate2 on Fly. Verified all 10 steps via admin-ops.

See `~/.claude/projects/-Volumes-SATECHI2TB-userfolder-Odoo/memory/project_saas_plan.md` for the complete fix log from 17 drill iterations.
