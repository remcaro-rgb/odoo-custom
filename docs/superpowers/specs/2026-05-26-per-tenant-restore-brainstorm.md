# Per-tenant rollback isolation — brainstorm primer

**Status:** brainstorm input, not a design decision. Operator picks the
implementation path; this document captures the ground truth the
brainstorm should reason over.

Companion to Tier 5 Item 2 of
[`2026-05-16-promote-to-prod-design.md`](./2026-05-16-promote-to-prod-design.md).

## Problem

Today's `rollback.py` SSH-delegates `pgbackrest --stanza=shared restore`
to `odoo-saas-postgres`. pgbackrest restore is **cluster-wide** — it
stops Postgres, wipes the data dir, replays WAL from S3 into the dir.
**Every tenant on the cluster reverts together.** That's
catastrophe-recovery semantics, not per-tenant-rollback semantics.

We need: roll back tenant X's data to before migration job Y, leave
tenant Z untouched.

## Ground truth we already have (don't re-derive)

### Topology
- **One Postgres cluster** per platform (Fly + Railway), each running
  our own image with `pgbackrest` configured (`stanza=shared`, S3
  archive, full + diff cadence in `pgbackrest-backup.yml`).
- **One DB per tenant** inside that cluster. Provisioned via
  `_create_empty_database(<db_name>)` in
  `custom-addons/saas_provisioning_gateway/controllers/provision.py`.
- `<db_name>` is the tenant slug (e.g. `acmesas2`).
- Tenant DBs share the cluster's WAL stream and pgbackrest stanza.
- Fly Postgres VM today: `shared-cpu-2x`, 4GB RAM, single volume, iad
  region only (Phase 5 will add GRU/SCL).

### Snapshot / restore code surface (Tier 5 wiring)
- `snapshot.py::_snapshot_via_ssh` already supports
  `PGBACKREST_SSH_APP` env override → target a non-default Postgres app
  (useful for staging variant).
- `rollback.py::_pgbackrest_argv` builds the SSH-delegated argv with
  the same `PGBACKREST_SSH_APP` knob.
- Sentinel-vs-real-label branch already exists in `rollback.run()`
  (line 130) — sentinel path uses `--type=time --target=<iso>`, real
  label uses `--set=<tag>`.

### Control plane
- `tenant_migration_jobs.snapshot_id` is a text column — currently
  holds either the pgbackrest tag (`20260524-065900F`) or the sentinel
  (`no-snapshot-<unix-ts>`).
- `tenants.db_name` available to map slug → DB.
- Drizzle schema lives at `~/Odoo-control-plane/packages/db/`.

## Three options to brainstorm

### A. Per-tenant Postgres apps

Spin up one Fly Postgres app per tenant
(`odoo-saas-postgres-<slug>`), each with own pgbackrest stanza + S3
prefix. `rollback.py` flips `PGBACKREST_SSH_APP` to the per-tenant
target.

| Dimension | Reading |
|---|---|
| Code change | Smallest — `_pgbackrest_argv` already takes the app from env. Provisioning gateway picks the per-tenant app at DB create. |
| Operational change | Largest — Fly app per tenant, secrets per tenant, deploy per tenant, monitoring per tenant. |
| Isolation | Strongest — compute, IO, restore, security boundary all per-tenant. |
| Cost | ~$15–20/mo per tenant (shared-cpu-2x + volume). 10 tenants ≈ $150–200/mo. 100 ≈ $1.5–2k/mo. |
| Cross-tenant queries | Impossible (separate clusters). |
| Filestore | Already per-tenant in S3, no change. |
| Migration path | Bulk: snapshot existing cluster → for each tenant, pg_dump → provision new per-tenant app → pg_restore. Expensive cutover. |
| Time to ship | Multi-week (provisioning + DR + monitoring rewires). |

### B. pg_dump / pg_restore per-tenant (with pgbackrest as DR floor)

Add a `pgdump` snapshot mode. `take_snapshot` runs `pg_dump -Fc -d
<db_name>` on the Postgres machine, uploads to
`s3://<bucket>/snapshots/<tenant>/<ts>.dump`, returns the S3 key as
`snapshot_id`. `rollback.py` learns a `pgrestore` branch that downloads
+ runs `pg_restore --clean -d <db_name>`. pgbackrest cluster backups
stay for catastrophic full-cluster DR.

| Dimension | Reading |
|---|---|
| Code change | Medium — new `_snapshot_via_pgdump` + new `_rollback_via_pgrestore` branch in rollback.run(). No infra change. |
| Operational change | Smallest — same cluster, same Fly app, same secrets. Adds an S3 prefix. |
| Isolation | Restore is per-tenant; compute/IO still shared. |
| Cost | Negligible. Only S3 storage delta (~30MB compressed per tenant per snapshot). |
| Cross-tenant queries | Still possible (same cluster). |
| Filestore | Unchanged. |
| Migration path | None — backfill snapshots on first promote of each tenant. |
| Time to ship | Days. Code only. |
| Caveats | pg_dump is logical → no transaction-consistent PITR (only the dump moment is restorable, not arbitrary times between dumps). Locks during dump (Odoo-internal load only, on schema-changing migrations operator-initiated anyway). |
| DR floor | Cluster-wide pgbackrest keeps running on the schedule it has now. |

### C. Logical replication slot per tenant + replica

Stream per-tenant changes to a parallel replica via Postgres logical
replication. Roll back by promoting the replica to a point-in-time and
swapping the tenant's DSN.

| Dimension | Reading |
|---|---|
| Time to ship | Weeks. |
| Operational complexity | High (slot management, replica lag, swap orchestration). |
| Verdict | Defer-defer per operator's Tier 5 brief. |

## Questions for the brainstorm

1. **Tenant count trajectory.** How many active tenants today? 6m-12m
   projection? (10 → B is obviously cheaper; 100+ → A's cost is
   tolerable if compute/IO isolation is a real ask.)
2. **Is compute isolation a customer ask?** If a noisy-neighbor tenant
   has bothered anyone, A pays for itself. If not, B's "shared compute
   is fine" assumption holds.
3. **Acceptable rollback granularity.** B's pg_dump captures the
   tenant at the moment the snapshot ran (pre-migration). Is that
   enough, or do we need arbitrary-PITR per tenant?
4. **DR-floor expectations.** B keeps cluster-wide pgbackrest as DR
   floor. A loses that for individual tenant clusters unless we run
   per-tenant pgbackrest too (more setup).
5. **What's the Tier 5 acceptance drill we want to actually pass?**
   Operator brief says: "promote tenant1 + tenant2 → SHA-B, rollback
   ONLY tenant1, tenant2 intact". Both A and B pass this. Picking the
   cheaper one to pass that drill first leaves room to upgrade later.

## Pre-brainstorm recommendation (operator can override)

**B (pg_dump per-tenant), with pgbackrest cluster backups as DR
floor.** Reasoning:
- Smallest code change (a few hundred LOC in `snapshot.py` +
  `rollback.py`).
- Zero infra change.
- Cost stays flat.
- Passes the Tier 5 acceptance drill.
- "Shared compute" tradeoffs are independent of rollback isolation —
  if compute isolation becomes a real customer ask later, A can be
  layered on top without throwing away B.

Operator owns the decision; this is a starting position for the
brainstorm, not the conclusion.
