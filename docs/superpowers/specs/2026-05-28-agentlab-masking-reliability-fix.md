# Agentlab masking — fail loud, stay connected, smoke-check structural tables

**Date:** 2026-05-28
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** #143
**Severity:** high (A) / medium (B)

---

## 1. Symptom

Manual `agentlab-daily-restore -f dry_run=false` (run `26582139424`) masked
`acmesas2` and `demo` cleanly but `operator` failed:

```
{"event": "mask.error", "db": "operator", "msg": "masking failed: connection already closed"}
{"event": "mask.fail",  "msg": "masking failed for one or more databases", "databases": ["operator"]}
```

`mask_prod_data.py` returned exit 1 — yet the **job reported success (✓)**.

## 2. Repro

- **A:** any masker non-zero exit while the step runs `python3 … | tee` — the
  job passes regardless (the `operator` failure above did).
- **B:** mask a large tenant over the flyctl proxy; ~13 min in, the
  connection drops with "connection already closed".

## 3. Affected tenants & severity

- **A (high):** a failed/rolled-back mask passes CI and leaves the tenant
  **unmasked in agentlab** — silent PII exposure in the lower-trust env.
- **B (medium):** large tenants can't finish masking; combined with A they
  fail silently.

## 4. Root cause

- **A:** the masking step runs `python3 mask_prod_data.py … | tee
  /tmp/masking.log`. The GitHub runner's default shell here does **not** set
  `pipefail` (confirmed empirically — the step passed despite exit 1), so the
  pipeline takes `tee`'s exit (0). The masker's exit codes (1 connection/
  config, 2 surviving PII) are discarded. `mask_database` rolls the whole DB
  transaction back on failure, so the tenant is left unmasked.
- **B:** the long-running masking connection has no TCP keepalives and no
  retry, so a transient proxy/idle drop aborts the whole tenant.

## 5. Proposed fix

### A — fail loud (`.github/workflows/agentlab-daily-restore.yml`)
`set -euo pipefail` at the top of the masking step **and** the dry-run-check
step, so a non-zero masker exit fails the workflow (and the restore won't
redeploy agentlab with unmasked data).

### B — stay connected (`infra/agentlab/mask_prod_data.py`)
- `_connect()` wrapper applies libpq **TCP keepalives** to every connection
  (`keepalives=1`, idle 30s, interval 10s, count 5).
- `_mask_database_with_retry()` retries `mask_database` up to 3× on
  `OperationalError`/`InterfaceError` (transient drops) with backoff;
  deterministic `RuntimeError` column clashes are **not** retried.
  `mask_database` rolls back fully on failure, so a retry re-masks cleanly.

### Smoke — structural integrity (the #142 "option 3", lightweight form)
`verify_structural_integrity()` runs after each DB is masked: it samples the
**structural tables** for masker markers (`MASKED:` / `[REDACTED`) and fails
the run (exit 2) if any appear — i.e. the structural-table skip (#140)
regressed and the snapshot would not survive `odoo -u all`.

**Scope note:** only structural *tables* are smoke-checked here. The
reference-column dimension of the smoke belongs with #144 (reference
passthrough) — adding it on this branch, which lacks #144, would fail the
nightly on the still-masked reference fields. A full `odoo -u all` post-mask
smoke was considered but is too heavy/unverifiable for the nightly;
`migration-dry-run-staging` already provides the real load check post-merge.

## 6. Regression test

`infra/agentlab/tests/test_masking.py` (112 passing): `is_masked_value`
recognises the `MASKED:<hash>,id` reference token shape (#142) that the smoke
relies on. `_connect` / `_mask_database_with_retry` / `verify_structural_integrity`
are DB-layer (validated by the daily-restore run, per the suite's convention).

## 7. Rollout

- A is high (PII-exposure control) → land promptly. Independent of #144 (own
  branch) so it isn't gated on the #142 security review.
- Security-adjacent (A restores a PII gate) — loop in security on review.
- **Operational note:** `operator` is currently unmasked in agentlab from run
  `26582139424`; re-mask or drop it (its large size will exercise fix B).
- Verification: unit tests in CI; full effect proven by the next real
  `agentlab-daily-restore -f dry_run=false` (watch for `mask.structural.clean`,
  any `mask.database.retry`, and a loud failure if a tenant can't mask).
