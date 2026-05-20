-- saas.tenant + saas_tenant_migration_job — control-plane DDL for Phase 4
--
-- Implements docs/superpowers/specs/2026-05-16-tenant-migration-queue-design.md §5
-- (data model) and §6 (job lifecycle).
--
-- Location: control-plane Postgres (Neon), reached via CONTROL_PLANE_PG_DSN.
-- The corresponding Drizzle schema lives in the Odoo-control-plane repo;
-- this SQL is the source-of-truth that the Drizzle migration mirrors.
--
-- Why this file even though the control plane is the canonical owner:
--   1. The promote-to-prod workflow (Phase 3, this repo) reads/writes
--      these tables via psql. Having the column shape committed alongside
--      the workflows that depend on it catches drift early.
--   2. Operators applying schema-only changes (e.g. an emergency column
--      addition before the Drizzle migration ships) have a single place
--      to grab the DDL from.
--   3. Future-portability: if we ever fold migration-queue ownership
--      back into Odoo (control plane Odoo instance), the model maps
--      cleanly to these tables.

-- --------------------------------------------------------------------------
-- saas.tenant — control-plane row per provisioned tenant
-- --------------------------------------------------------------------------
-- This is the AUTHORITATIVE record of what tenants exist, which pool/wave
-- they live in, and what SHA they were last migrated to. Tenant *data*
-- lives in per-tenant Postgres DBs in the data plane; this row is the
-- index that lets the control plane talk about a tenant.
--
-- Idempotent: ALTER ... ADD COLUMN IF NOT EXISTS shape so we can layer
-- the Phase 4 additions onto an existing table.

CREATE TABLE IF NOT EXISTS saas.tenant (
    id                  bigserial PRIMARY KEY,
    name                text NOT NULL UNIQUE,         -- tenant slug (= Odoo DB name)
    pool_id             text NOT NULL,                -- Railway / Fly pool identifier
    state               text NOT NULL DEFAULT 'active',  -- active | suspended | deleted
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Phase 4 columns. ADD IF NOT EXISTS lets this re-run safely.
ALTER TABLE saas.tenant
    ADD COLUMN IF NOT EXISTS wave text DEFAULT 'canary';
ALTER TABLE saas.tenant
    ADD COLUMN IF NOT EXISTS last_migrated_sha text;
ALTER TABLE saas.tenant
    ADD COLUMN IF NOT EXISTS size_bucket text;
ALTER TABLE saas.tenant
    ADD COLUMN IF NOT EXISTS maintenance_window text NOT NULL DEFAULT '0 2 * * *';
ALTER TABLE saas.tenant
    ADD COLUMN IF NOT EXISTS tz text NOT NULL DEFAULT 'America/Bogota';

-- wave constraint — must be one of the recognized values OR NULL ('paused' is
-- explicit and set by the runner on tenant migration failure, freezing the
-- tenant out of subsequent waves until an operator unpauses).
ALTER TABLE saas.tenant
    DROP CONSTRAINT IF EXISTS saas_tenant_wave_known;
ALTER TABLE saas.tenant
    ADD CONSTRAINT saas_tenant_wave_known
    CHECK (wave IS NULL OR wave IN ('canary', 'w1', 'w2', 'paused'));

-- size_bucket constraint — set by the daily cron based on tenant DB size.
ALTER TABLE saas.tenant
    DROP CONSTRAINT IF EXISTS saas_tenant_size_bucket_known;
ALTER TABLE saas.tenant
    ADD CONSTRAINT saas_tenant_size_bucket_known
    CHECK (size_bucket IS NULL OR size_bucket IN ('xs', 's', 'm', 'l', 'xl'));

CREATE INDEX IF NOT EXISTS saas_tenant_wave_idx   ON saas.tenant (wave);
CREATE INDEX IF NOT EXISTS saas_tenant_pool_idx   ON saas.tenant (pool_id);
CREATE INDEX IF NOT EXISTS saas_tenant_state_idx  ON saas.tenant (state) WHERE state != 'active';

-- --------------------------------------------------------------------------
-- saas_tenant_migration_job — the FIFO queue per spec §5
-- --------------------------------------------------------------------------
-- Plural-form table; Drizzle convention is snake_case. The promote-to-prod
-- workflow (Phase 3) INSERTs into this; runners (Phase 4 §7) SELECT FOR
-- UPDATE SKIP LOCKED to claim one job at a time.

CREATE TABLE IF NOT EXISTS saas_tenant_migration_job (
    id                  bigserial PRIMARY KEY,
    tenant_id           bigint NOT NULL REFERENCES saas.tenant(id),
    target_sha          text NOT NULL,
    status              text NOT NULL DEFAULT 'queued',  -- see CHECK below
    timeout_minutes     integer NOT NULL DEFAULT 30,
    started_at          timestamptz,
    finished_at         timestamptz,
    snapshot_id         text,     -- pgbackrest snapshot taken before migration
    log_url             text,     -- artifact-store link to runner log
    error_excerpt       text,     -- last 50k of stderr on failure
    retry_count         integer NOT NULL DEFAULT 0,
    enqueued_by         text,     -- GHA run id that enqueued ("promote-to-prod-<run_id>")
    enqueued_at         timestamptz NOT NULL DEFAULT now(),
    heartbeat_at        timestamptz,  -- runner pings every 60s while running
    CONSTRAINT saas_tenant_migration_job_status_known
        CHECK (status IN ('queued','blocked','running','done','failed','skipped','timedout'))
);

-- Per spec §6 / §7:
--   - Runner picks the OLDEST queued or blocked job whose maintenance window
--     is open: ORDER BY enqueued_at; both queued and blocked are eligible
--     each cycle, blocked is just "checked again later".
--   - Concurrent runners use FOR UPDATE SKIP LOCKED on a SELECT that
--     filters by status='queued'/'blocked', so they don't fight.
--   - Stale-running detection (spec §12 — runner crashed) finds rows in
--     status='running' with heartbeat_at < now() - 2*timeout_minutes, and
--     auto-resets them to 'queued' with retry_count += 1.

CREATE INDEX IF NOT EXISTS saas_tenant_migration_job_status_idx
    ON saas_tenant_migration_job (status, enqueued_at);
CREATE INDEX IF NOT EXISTS saas_tenant_migration_job_tenant_idx
    ON saas_tenant_migration_job (tenant_id);
CREATE INDEX IF NOT EXISTS saas_tenant_migration_job_target_idx
    ON saas_tenant_migration_job (target_sha);
-- Partial index for the runner heartbeat sweep — cheap, only the small
-- set of running jobs is included.
CREATE INDEX IF NOT EXISTS saas_tenant_migration_job_running_heartbeat_idx
    ON saas_tenant_migration_job (heartbeat_at)
    WHERE status = 'running';

-- --------------------------------------------------------------------------
-- size-bucket auto-compute (cron-driven; see runbook for the cron job)
-- --------------------------------------------------------------------------
-- A view (not a generated column) so the daily cron can update size_bucket
-- after measuring each tenant DB. The pg_database_size() approach requires
-- USAGE on the tenant DBs, which the control-plane role doesn't have; we
-- compute it data-plane-side and UPDATE saas.tenant.size_bucket here.

-- Helper to map a byte count to a bucket.
CREATE OR REPLACE FUNCTION saas.tenant_size_bucket(bytes bigint) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF bytes IS NULL THEN RETURN NULL;
    ELSIF bytes < 1024::bigint * 1024 * 1024 THEN RETURN 'xs';        -- < 1 GB
    ELSIF bytes < 5::bigint * 1024 * 1024 * 1024 THEN RETURN 's';     -- 1-5 GB
    ELSIF bytes < 20::bigint * 1024 * 1024 * 1024 THEN RETURN 'm';    -- 5-20 GB
    ELSIF bytes < 50::bigint * 1024 * 1024 * 1024 THEN RETURN 'l';    -- 20-50 GB
    ELSE RETURN 'xl';                                                  -- > 50 GB
    END IF;
END;
$$;
