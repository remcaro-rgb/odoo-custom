# Agentlab Environment — Design Spec

**Date:** 2026-05-16
**Author:** Manu (drafted with Claude)
**Status:** Draft
**Spec type:** design spec
**Scope of work:** new Fly app `odoo-saas-odoo-agentlab` + its Postgres + masked-restore pipeline. The sandbox all six agents work against — never real staging or prod.

---

## 1. Goal

Provide a daily-refreshed clone of staging where agents can:

- Run code changes against realistic data.
- Reproduce bugs.
- Test migrations end-to-end.
- Run instrumented workflows for the Optimization Agent.
- Host per-spec preview environments (sharing the same base masked dataset).

Without ever touching real customer data.

---

## 2. Non-goals

- Replacing staging. Agentlab is a sandbox, not a pre-prod environment.
- Hosting per-tenant production-equivalent data. All data is masked.
- Long-term storage. Daily restore wipes whatever was there.
- Production-grade SLOs. Best-effort.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│ staging-fly Postgres (existing)                         │
│         │                                               │
│         │ nightly pgbackrest snapshot (existing)        │
│         ▼                                               │
│ S3 / Cloudflare R2 (encrypted, existing)               │
│         │                                               │
│         │ daily restore-with-masking pipeline (NEW)     │
│         ▼                                               │
│ ┌─────────────────────────────────────────────────┐    │
│ │ odoo-saas-odoo-agentlab-db (Fly Postgres) (NEW) │    │
│ └─────────────────────────────────────────────────┘    │
│                                                         │
│ ┌─────────────────────────────────────────────────┐    │
│ │ odoo-saas-odoo-agentlab (Fly app) (NEW)        │    │
│ │  - serves agent-driven test workflows           │    │
│ │  - serves Implementation Agent preview spawns   │    │
│ └─────────────────────────────────────────────────┘    │
│                                                         │
│ Isolated network egress:                                │
│  SMTP → MailHog · webhooks → mock · telemetry → mock   │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Tenancy impact

Tenancy boundary is preserved by **strict masking before any data enters agentlab**:

- Allow-list approach: columns are masked by default; only those in `infra/agentlab/mask-allowlist.yml` pass through unmasked.
- Allow-list is owned by `security-leads` CODEOWNERS; the Security Agent proposes additions (per its design spec §5.7).
- The masking script (`infra/agentlab/mask-prod-data.sh`) is the single point of trust — it's audited per release, tests cover it, and any change requires 2 security-leads approvals.
- A weekly sample audit picks 100 random rows from agentlab and asserts no PII patterns leak (Security Agent's job).

---

## 5. Data flow

### 5.1 Daily restore pipeline

`agentlab-daily-restore.yml` (cron `0 2 * * *`, after the existing staging pgbackrest snapshot):

```
1. Fetch latest staging pgbackrest snapshot from R2/S3.
2. Drop and recreate odoo-saas-odoo-agentlab-db Postgres.
3. Restore snapshot via pg_restore.
4. Run mask-prod-data.sh against all databases:
     - For every column NOT in mask-allowlist.yml:
         apply masking rule from masking-rules.yml (hash, redact, replace with fake)
     - Validate: sample 100 rows, assert no PII patterns
5. Restore the corresponding encrypted filestore snapshot (saas_filestore_backup v2).
6. Re-deploy the Fly app with the fresh DB credentials.
7. Run smoke probe: /web/health, login as test user.
8. Emit metrics: snapshot age, restore duration, masking duration.
```

### 5.2 Sub-tenant DBs for preview envs

Implementation Agent's preview envs share the Postgres but use isolated DBs:

```
odoo-saas-odoo-agentlab-db:
   ├── agentlab             (the shared masked dataset)
   ├── preview_1500         (Implementation Agent for spec 1500)
   ├── preview_1501         (...)
   └── ...
```

Each preview DB is a copy of `agentlab` (template approach: `CREATE DATABASE preview_N TEMPLATE agentlab`). Cheap (~30s) and isolated.

### 5.3 Networking

- Egress firewall rules: only allow outbound to:
  - GitHub (for agent operations)
  - Anthropic + LiteLLM endpoints (for agent LLM calls)
  - MailHog (for outbound SMTP)
  - Mock-webhook receiver (for any tenant webhooks)
- Block all other egress at the Fly app level.

### 5.4 Inbound

- HTTPS via Traefik on `agentlab.<your-domain>` and `preview-*.<your-domain>`.
- Wildcard cert for preview-*.
- Auth: standard Odoo session for agentlab; one-time-password for preview envs (per Implementation Agent design §6.3).

---

## 6. Cost model

| Component | Monthly cost |
|---|---|
| Fly app `odoo-saas-odoo-agentlab` (`shared-cpu-2x`, auto-stop) | ~$10 |
| Fly Postgres (5 GB, snapshots) | ~$5 |
| R2/S3 storage for snapshots | ~$2 |
| **Base agentlab cost** | **~$17** |
| Up to 10 concurrent preview envs (~$5 each) | up to ~$50 |
| **Total** | **~$67** |

Well within the v6 spend caps.

---

## 7. Security model

- Network egress restricted (above).
- Postgres credentials rotated quarterly.
- Mask allow-list under CODEOWNERS approval.
- Audit: every restore + every masking run writes to `saas.audit.event`.
- No real customer data ever reaches agentlab — masking is the only path.
- Reviewer logins on preview envs are one-time, group_user only.

---

## 8. Test plan

### Unit
- `mask-prod-data.sh` over a fixture DB → all PII patterns redacted.
- Allow-list parsing rejects malformed entries.

### Integration
- End-to-end nightly restore → smoke probe passes; freshness ≤ 26 h.
- Preview env spawn from agentlab template → < 60 s; isolated from other previews.

### Negative
- Restore with allow-list entry for a non-existent column → fail loudly, not silently.
- Run masking on a DB with unmasked PII pattern in allow-listed column → security audit flag.

---

## 9. Rollout plan

Phase 5 of v7 (weeks 7–8). Sub-phases:
- **5a (week 7):** Provision Fly app + Postgres. Stub data (no masked-restore yet).
- **5b (week 7):** Implement masking pipeline against a fixture snapshot.
- **5c (week 8):** Wire daily cron. Restore from real staging snapshot.
- **5d (week 8):** Smoke probes + audit log integration. Documented runbook.

---

## 10. Observability

- Daily restore success/failure metric.
- Snapshot age dashboard (target < 26 h).
- Masking-pass duration.
- Per-PII-pattern violation counter (should always be 0 in production).
- Active preview env count + per-preview cost.

Alerts:
- Restore failure → page on-call.
- Snapshot age > 30 h → page on-call.
- Masking violation detected (audit pass) → page security-leads immediately.
- Egress to non-allowed destination detected → security alert.

---

## 11. Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Restore fails | Nightly cron failure alarm | Re-run; if still failing, fall back to previous day's snapshot |
| Masking script bug leaves PII | Weekly audit | Pause new previews; alert security-leads; fix; re-restore |
| Allow-list expanded mistakenly | Code review at PR time | Require 2 security-leads approvals on allow-list changes |
| Egress restriction misconfigured (real egress allowed) | Periodic fly-side audit | Alert security; fix; re-test |
| Preview-DB explosion (forgot to clean up) | Hourly cron checks count | preview-cleanup.yml destroys stale envs |
| Postgres disk fills | Disk usage alarm | Scale volume; clean old previews |

---

## 12. Open questions

1. Snapshot frequency — once daily is the default. Some agents would benefit from more frequent (every 6h). Trade-off: cost vs data freshness.
2. Cross-region disaster recovery — should agentlab itself have a backup region? Probably not; it's a sandbox.
3. Should preview envs use a private DB per env, or a schema in the shared agentlab DB? Trade-off: isolation vs cost.
4. Long-running developer access — can a dev "claim" agentlab for 24h to debug, pausing the nightly restore? Probably yes via a manual lock.
