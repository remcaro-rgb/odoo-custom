-- saas.audit.event — append-only audit log
--
-- Source of truth for the DDL the control-plane Postgres must hold.
-- Apply via `psql "$CONTROL_PLANE_PG_DSN" -f saas-audit-event-schema.sql`.
-- See infra/runbooks/saas-audit-event.md for the protocol (who writes
-- what, when, and how to query for forensics).
--
-- The data-plane GitHub Actions workflows that insert into this table:
--   .github/workflows/preview-cleanup.yml      action='preview-env-destroyed'
--   .github/workflows/rollback-prod.yml        action='rollback-prod'
--   .github/workflows/promote-to-prod.yml      action='promote-to-prod' (Phase 3)
--   .github/workflows/agentlab-daily-restore.yml  action='agentlab-restored' (Phase 5)
--
-- All three are aware of the schema below and write columns that match.
-- Adding a new event source: pick a unique action, document the payload
-- shape in the runbook, INSERT here with CONTROL_PLANE_PG_DSN.

-- --------------------------------------------------------------------------
-- Schema container.
-- --------------------------------------------------------------------------
-- Why a dedicated schema (not the default `public`):
--   1. Append-only triggers are scoped per-schema; isolating audit objects
--      from operational tables makes RBAC simpler ("audit_reader" role can
--      USAGE the schema but nothing else).
--   2. Future audit object types (saas.audit.export_run, saas.audit.review)
--      live alongside without polluting `public`.
CREATE SCHEMA IF NOT EXISTS saas_audit;

-- --------------------------------------------------------------------------
-- The event table.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saas_audit.event (
    id              bigserial PRIMARY KEY,
    ts              timestamptz NOT NULL DEFAULT now(),
    actor_kind      text NOT NULL,    -- 'human' | 'agent' | 'system'
    actor_name      text NOT NULL,    -- 'manu' | 'agent:implementation' | 'cron:nightly-restore'
    action          text NOT NULL,    -- 'promote-to-prod' | 'rollback' | 'preview-env-destroyed' | ...
    target_kind     text,             -- 'tenant' | 'sha' | 'pr' | 'preview' | 'snapshot' | null
    target_id       text,             -- free-form id paired with target_kind
    sha             text,             -- git commit involved (if any)
    wave            text,             -- 'canary' | 'w1' | 'w2' | 'all' | null
    reason          text,             -- human-supplied free text (rollback paste-back, escalation note)
    payload         jsonb,            -- additional structured context
    request_id      text,             -- correlation id (matches the request_id tag on logs)

    -- Sanity constraints (cheap; defends against caller typos).
    CONSTRAINT saas_audit_event_actor_kind_known
        CHECK (actor_kind IN ('human', 'agent', 'system')),
    CONSTRAINT saas_audit_event_wave_known
        CHECK (wave IS NULL OR wave IN ('canary', 'w1', 'w2', 'all', 'hotfix'))
);

-- Hot path is "find events in time range, optionally filtered by actor or action".
CREATE INDEX IF NOT EXISTS saas_audit_event_ts_idx
    ON saas_audit.event (ts DESC);
CREATE INDEX IF NOT EXISTS saas_audit_event_actor_idx
    ON saas_audit.event (actor_kind, actor_name);
CREATE INDEX IF NOT EXISTS saas_audit_event_action_idx
    ON saas_audit.event (action);
CREATE INDEX IF NOT EXISTS saas_audit_event_target_idx
    ON saas_audit.event (target_kind, target_id);

-- --------------------------------------------------------------------------
-- Append-only enforcement.
-- --------------------------------------------------------------------------
-- The trigger fires BEFORE UPDATE / BEFORE DELETE on any row and raises;
-- nothing — not even the table owner — can modify history. Adopt-by-truncate
-- and DROP TABLE are still possible, but those require a DDL operation that
-- shows up in pg_stat_activity and the audit log of the *control plane*
-- itself, so they're inherently visible.
--
-- Compliance retention is layered on top via the nightly S3 Object-Lock
-- export (cf. observability-stack-design.md §7); even if a determined
-- attacker drops the schema, the prior day's snapshot survives.

CREATE OR REPLACE FUNCTION saas_audit.event_no_modify() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'saas_audit.event is append-only (TG_OP=%)', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

DROP TRIGGER IF EXISTS saas_audit_event_no_update ON saas_audit.event;
CREATE TRIGGER saas_audit_event_no_update
    BEFORE UPDATE ON saas_audit.event
    FOR EACH ROW EXECUTE FUNCTION saas_audit.event_no_modify();

DROP TRIGGER IF EXISTS saas_audit_event_no_delete ON saas_audit.event;
CREATE TRIGGER saas_audit_event_no_delete
    BEFORE DELETE ON saas_audit.event
    FOR EACH ROW EXECUTE FUNCTION saas_audit.event_no_modify();

-- --------------------------------------------------------------------------
-- RBAC (optional but recommended).
-- --------------------------------------------------------------------------
-- Two intended roles:
--   audit_writer  — used by the workflows. INSERT only.
--   audit_reader  — used by humans and auditors via Grafana / psql.
--                   SELECT only on saas_audit.event.
-- The bootstrap commands are commented out because the control-plane
-- Postgres may already have its own role conventions. Adapt + uncomment
-- when applying.
--
--   CREATE ROLE audit_writer NOINHERIT;
--   GRANT USAGE ON SCHEMA saas_audit TO audit_writer;
--   GRANT INSERT ON saas_audit.event TO audit_writer;
--   GRANT USAGE ON SEQUENCE saas_audit.event_id_seq TO audit_writer;
--
--   CREATE ROLE audit_reader NOINHERIT;
--   GRANT USAGE ON SCHEMA saas_audit TO audit_reader;
--   GRANT SELECT ON saas_audit.event TO audit_reader;
