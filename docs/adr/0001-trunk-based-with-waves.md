# 0001. Trunk-based development with per-client waves

**Date:** 2026-05-15
**Status:** Accepted

## Context

We run a multi-tenant Odoo SaaS where all clients share the same image but their data, configuration, and enabled modules differ. We need a branching and rollout model that:

1. Keeps engineering simple (no per-client codebase).
2. Lets us stage risk so a bad change doesn't take everyone down.
3. Allows a single client to be rolled forward or paused independently when needed.
4. Doesn't slow down the everyday change cadence with ceremony.
5. Survives a small team (2–4 engineers in 2026).

Alternatives we considered: per-client branches; release branches (`release/2026.05`); long-lived feature branches.

## Decision

We will use **trunk-based development on `main`** with **short-lived feature branches** (squash-merged) and **per-client rollout waves** controlled by data on `saas_tenant_gate`, not by code.

The wave model is:

- `canary` — 1–2 friendly tenants who opted in.
- `w1` — low-risk tenants (small DBs, no historical data sensitivity).
- `w2` — everyone else.

Each tenant carries `wave`, `pool_id`, and `last_migrated_sha` fields on `saas.tenant`. Promotion is via the `promote-to-prod` GHA workflow with `wave` as a parameter. A per-tenant migration queue (`saas.tenant.migration.job`) ensures failures isolate to one tenant rather than blocking the whole wave.

## Consequences

**Easier:**
- No branch sprawl. `main` is always deployable.
- A bad change is contained: only canary tenants see it during the soak window.
- Per-tenant emergency pause is a single field flip (`tenant.wave = 'paused'`).
- Feature flags + module install state give us in-image flexibility without code forks.

**Harder:**
- Need discipline around feature flags to ship new behaviour dark. If a change touches user-visible behaviour, it must be flag-wrapped or be willing to ship to all canary tenants at once.
- Long-running per-tenant migrations require the `tenant_migration_queue` model + maintenance windows (per the per-tenant migration safety spec).
- DevOps must triage failed-tenant migrations actively; we can't just retry the wave.

## Alternatives considered

**Per-client branches.** Rejected — multiplies maintenance cost by N (tenants), and every cross-cutting change requires N merges. We'd lose the cross-platform parity guarantee fast.

**Release branches (`release/2026.05`).** Rejected — we'd still need a per-client overlay for differences, AND we'd have to backport fixes. Trunk-based wins on simplicity.

**Long-lived feature branches.** Rejected — encourages drift; squash-merge from short branches gives us the same review surface without the staleness.
