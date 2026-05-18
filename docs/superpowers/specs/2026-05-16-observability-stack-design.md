# Observability Stack — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** central log drain, per-tenant metrics, alerts, and the `saas.audit.event` append-only audit log. Implements ADR-0003 (Better Stack as default).

---

## 1. Goal

A single observability stack that gives operators, agents, and auditors a clear answer to:

- **What's happening right now** per tenant (logs + metrics + traces).
- **What changed when, by whom** (audit log).
- **What went wrong last incident** (forensic logs + traces).

Without being expensive to operate at our scale (~10 GB ingestion/day, ~50 tenants, 6 agents).

---

## 2. Non-goals

- Full APM (Datadog-level tracing). Defer until growth justifies.
- BI / analytics warehouse. Separate concern.
- User-behaviour analytics. Privacy-sensitive; needs a separate ADR.
- Real-time alerting < 30s. Best-effort 1–2 min.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────┐
│ Odoo workers (per tenant in prod pools)              │
│  · structured JSON logs to stdout                    │
│  · OpenTelemetry spans where instrumented            │
│                                                      │
│ Agents (per run, on the v7 runtime)                  │
│  · structured JSON logs via Logger port              │
│                                                      │
│ Support gateway (Fly app)                            │
│  · gateway_events table (Postgres)                   │
└────────────────┬─────────────────────────────────────┘
                 │ stdout → platform log forwarder
                 ▼
┌──────────────────────────────────────────────────────┐
│ Log drain (Better Stack — see ADR-0003)              │
│  · 30d hot retention                                 │
│  · 1y cold retention in S3                           │
│  · Tags: tenant, worker, request_id, agent, run_id   │
└──────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────┐
│ Grafana (Cloud) for dashboards                       │
│  · Per-tenant panel (filterable by wave)             │
│  · Per-agent panel                                   │
│  · SLO panel (5xx rate, p95)                         │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ saas.audit.event (Postgres, control plane)           │
│  · Append-only (trigger refuses UPDATE/DELETE)       │
│  · Nightly export to S3 with Object Lock             │
│  · Actor, action, target, sha, wave, reason          │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Alerting                                             │
│  · Better Stack Alerts → Slack + PagerDuty           │
│  · Per-tenant 5xx, migration fail, backup staleness  │
│  · Agent crash, spend cap, parity drift              │
└──────────────────────────────────────────────────────┘
```

---

## 4. Tenancy impact

Per-tenant observability is the headline. Every log line and metric carries a `tenant` tag. Per-tenant Grafana panels are auto-generated from a template (one panel per tenant, filterable by wave).

No tenant data is in logs without explicit redaction (Odoo's logging is configured to NOT log full request bodies; only request_id + status + duration).

---

## 5. Structured-log shape

Every log line emitted by Odoo + agents has this shape:

```json
{
  "ts": "2026-05-16T14:23:11.123Z",
  "level": "info",
  "msg": "request handled",
  "tenant": "acme",
  "worker": "odoo-saas-odoo-prod.pid-12345",
  "request_id": "req_8a3b9f...",
  "method": "POST",
  "path": "/web/dataset/call_kw",
  "status": 200,
  "duration_ms": 142,
  "user_id": 7,
  "addon": "club_pos",
  "model": "pos.order",
  "agent": null,
  "run_id": null
}
```

For agent runs:

```json
{
  "ts": "...",
  "level": "info",
  "msg": "implementation.plan_drafted",
  "agent": "implementation",
  "run_id": "r_42",
  "issue": 1500,
  "pr": 1501,
  "phase": "plan",
  "duration_ms": 4321,
  "model": "claude-sonnet-4-6",
  "cost_usd": 0.42,
  "tokens_in": 5210,
  "tokens_out": 1340,
  "tenant": null
}
```

The `tenant`, `agent`, and `request_id` fields are the join keys that make end-to-end tracing possible across services.

---

## 6. Per-tenant metrics

Pushed from Odoo workers via OpenTelemetry → Grafana Cloud (separate from Better Stack which is for logs):

| Metric | Type | Labels |
|---|---|---|
| `odoo_http_requests_total` | counter | tenant, status |
| `odoo_http_duration_seconds` | histogram | tenant, path_template |
| `odoo_login_success_total` | counter | tenant |
| `odoo_login_failure_total` | counter | tenant |
| `odoo_worker_memory_bytes` | gauge | tenant, worker |
| `odoo_worker_cpu_seconds_total` | counter | tenant, worker |
| `pg_connections_active` | gauge | tenant |
| `saas_audit_events_total` | counter | actor_kind, action |
| `saas_tenant_migration_jobs_total` | counter | wave, status |

Per-tenant dashboard built from a Grafana template:

- 5xx rate
- p95 page load
- login success/failure
- worker memory + CPU
- DB connections active
- recent audit events (last 24h)

---

## 7. The `saas.audit.event` table

```sql
CREATE TABLE saas.audit.event (
    id              bigserial primary key,
    ts              timestamptz default now(),
    actor_kind      text not null,           -- human | agent | system
    actor_name      text not null,           -- 'manu' | 'agent:implementation' | 'cron:nightly-restore'
    action          text not null,           -- 'promote-to-prod' | 'rollback' | 'feature-flag-flip' |
                                             -- 'spec-merged' | 'agent-pr-merged' | 'preview-spawned' |
                                             -- 'snapshot-restored' | 'tenant-paused' | ...
    target_kind     text,                    -- tenant | sha | pr | preview | snapshot
    target_id       text,
    sha             text,
    wave            text,
    reason          text,
    payload         jsonb,                   -- additional context (free-form)
    request_id      text                     -- correlation
);

CREATE INDEX saas_audit_event_ts_idx ON saas.audit.event (ts DESC);
CREATE INDEX saas_audit_event_actor_idx ON saas.audit.event (actor_kind, actor_name);
CREATE INDEX saas_audit_event_action_idx ON saas.audit.event (action);
CREATE INDEX saas_audit_event_target_idx ON saas.audit.event (target_kind, target_id);

-- Append-only enforcement
CREATE OR REPLACE FUNCTION saas.audit_event_no_modify() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'saas.audit.event is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER saas_audit_event_no_update
    BEFORE UPDATE ON saas.audit.event
    FOR EACH ROW EXECUTE FUNCTION saas.audit_event_no_modify();

CREATE TRIGGER saas_audit_event_no_delete
    BEFORE DELETE ON saas.audit.event
    FOR EACH ROW EXECUTE FUNCTION saas.audit_event_no_modify();
```

Nightly export to S3 with Object Lock (compliance retention).

---

## 8. Alert catalogue

Severity: `page` (PagerDuty), `warn` (Slack), `info` (Slack).

| Alert | Trigger | Severity |
|---|---|---|
| Per-tenant 5xx burst | rate > 5/min for 5 min | page |
| Per-tenant login failure spike | rate > 10/min for 5 min | warn |
| Migration job failed | any tenant in any wave | page |
| Cross-platform parity drift | Railway green / Fly red (or vice versa) | warn |
| Backup snapshot older than 24h | nightly check | page |
| Agent crashed | non-zero exit on cron run | warn |
| Agent spend > 80% of cap | weekly | warn |
| Agent spend > 100% of cap | hits | page (pauses agent) |
| Concurrent preview envs ≥ 9 | approaching cap | warn |
| Preview env spawn failed | per attempt | warn |
| Implementation Agent escalation rate > 15% | rolling 7d | warn |
| Hotfix at 36h without retro brief | cron | warn |
| Hotfix at 48h without retro brief | cron | page |
| Sensitive-topic detection accuracy < 95% | weekly audit | warn |
| Audit log export to S3 failed | nightly | page |
| saas.audit.event UPDATE/DELETE attempted | trigger | page (security) |
| LLM provider outage (LiteLLM fallback active > 1h) | observed | warn |

---

## 9. Security model

- Log drain credentials rotated quarterly.
- Per-tenant tagging strict: any log line without a `tenant` tag from an Odoo worker is a bug; fail CI.
- PII redaction: Odoo's logger configured to NOT log request bodies; only `path_template` (anonymised).
- Audit log: append-only, S3 Object Lock, RBAC restricts read access.
- Grafana: separate read-only role for auditors; full access for `prod-deployers` only.

---

## 10. Test plan

### Unit
- Logger adapter emits the documented JSON shape for every log call.
- Audit-trigger refuses UPDATE and DELETE.

### Integration
- Send a planted log line; verify it arrives in Better Stack within 60 s with the right tags.
- Insert audit event; verify export pipeline captures it nightly.

### E2E (smoke)
- Run a full Implementation Agent flow; verify end-to-end correlation via `run_id` across logs, metrics, audit.

---

## 11. Rollout plan

Phase 5 of the v7 master roadmap (weeks 7–8). Sub-phases:

- **5a (week 7):** Better Stack account + log drain wired in from Odoo workers.
- **5b (week 7):** Agent Logger adapter implementation (default StdJSON → Better Stack via stdout forwarder).
- **5c (week 8):** Per-tenant metrics + Grafana dashboard template.
- **5d (week 8):** Audit log model + S3 export.
- **5e (week 8):** Alert catalogue wired with severities to Slack + PagerDuty.

---

## 12. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Log drain ingest outage | Self-monitoring (heartbeat log not received) | Fall back to in-VM rsyslog buffer; replay when service returns |
| Better Stack pricing surprise | Monthly cost dashboard | Migrate to self-hosted Loki (per ADR-0003 plan B) |
| Audit log fills disk | Disk usage alarm | Archive older rows to S3 (with Object Lock); table partitioning |
| PII leaks in logs | Periodic regex audit | Patch logger; rotate logs; security review |
| Grafana down during incident | Direct query Better Stack | Runbook covers this fallback |

---

## 13. Open questions

1. Should we adopt full OpenTelemetry traces (not just metrics) for Odoo? Cost is modest; value is debuggable cross-service flows.
2. Audit-log read access — who's the auditor role? External compliance person, or internal-only?
3. Better Stack vs Grafana Cloud Logs — should we consolidate on Grafana? Trade-off: Better Stack's UX vs single-vendor convenience.
4. Per-tenant cost attribution — bake into metrics now or defer?
