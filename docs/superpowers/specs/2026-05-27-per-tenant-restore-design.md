# Per-tenant rollback isolation — design (Option B)

**Status:** approved 2026-05-27 (operator pick after brainstorm against
[`2026-05-26-per-tenant-restore-brainstorm.md`](./2026-05-26-per-tenant-restore-brainstorm.md)).

Closes Tier 5 Item 2 of
[`2026-05-16-promote-to-prod-design.md`](./2026-05-16-promote-to-prod-design.md).

## Decision

Add a `pgdump` snapshot mode (logical pg_dump per tenant, uploaded to
S3) alongside the existing `cli`/`ssh`/`http`/`skip` modes. Rollback
learns a `pgrestore` branch that reads the dump and replays it into
the tenant's database via `pg_restore --clean --if-exists`.
Cluster-wide pgbackrest stays as DR floor for catastrophic recovery;
day-to-day per-tenant rollback uses pgdump.

Rejected: per-tenant Postgres Fly apps (Option A). Reason: cost
scales linearly with tenant count and we don't have a customer ask
for compute isolation. Option B leaves room to layer A on later if a
noisy-neighbor case emerges.

## What changes

### Surface that grows

| File | Change |
|---|---|
| `infra/postgres/Dockerfile` | Install `awscli` + ship two wrapper scripts (below) into `/usr/local/bin/` |
| `infra/postgres/pgdump-snapshot.sh` | New: `pg_dump -Fc -d <db> | aws s3 cp - s3://<bucket>/pgdump/<tenant>/<ts>.dump`. Prints `SNAPSHOT_KEY=<key>` for the runner to parse. |
| `infra/postgres/pgrestore-snapshot.sh` | New: `aws s3 cp s3://<bucket>/<key> - | pg_restore --clean --if-exists -d <db>` |
| `infra/runners/migration_runner/snapshot.py` | Add `_snapshot_via_pgdump()` + `mode == 'pgdump'` branch in `take_snapshot()`. |
| `infra/runners/migration_runner/rollback.py` | Detect pgdump-shaped `snapshot_id` (starts with `pgdump/`); add `_rollback_via_pgrestore()` branch in `run()`. Pre-existing pgbackrest `--set <label>` and PITR `--target=<time>` paths stay unchanged. |
| `infra/runners/migration_runner/tests/` | New `test_snapshot_pgdump.py` + extended `test_rollback_run.py` cases. |

### Surface that stays

- `_pgbackrest_argv`, `cli()`, `_finalize_ok` — unchanged (operator's
  Tier 5 "don't touch" list).
- `tenant_migration_jobs.snapshot_id` — text column; pgdump keys fit
  the existing shape (just a new prefix vocabulary).
- pgbackrest scheduled backups (`pgbackrest-backup.yml`) — keep
  running. They are the cluster DR floor.

## snapshot_id shape vocabulary

After this change, three forms exist in the wild:

| Form | Producer | Restore path |
|---|---|---|
| `20260527-120000F` or `20260524-065900F_20260527-065322I` | pgbackrest (`mode=ssh\|cli`) | `pgbackrest --set <label> --delta restore` (cluster-wide) |
| `pgdump/<tenant_slug>/<iso-ts>.dump` | pg_dump (`mode=pgdump`) | `aws s3 cp - | pg_restore --clean -d <db>` (per-tenant) |
| `no-snapshot-<unix-ts>` | sentinel (`mode=skip`) | pgbackrest PITR via `--type=time --target=<iso>` |

`rollback.run()` dispatches by prefix. The cluster-wide pgbackrest
path keeps existing semantics (existing rows continue to function;
zero migration). Going forward, new promotions write pgdump keys.

## S3 layout

Reuse the existing pgbackrest bucket (`goliatt-odoo-saas-hot`) with a
`pgdump/` subprefix. No new bucket, no new IAM. The pgbackrest IAM
creds already on the postgres machine (env
`PGBACKREST_REPO1_S3_KEY*`) cover this — wrapper scripts read them
via existing env. Lifecycle policy: 30 days hot retention (matches
pgbackrest archive retention).

```
s3://goliatt-odoo-saas-hot/
  pgbackrest-fly/                                # existing
  pgbackrest-railway/                            # existing
  pgdump/<tenant_slug>/<iso-ts>.dump             # new
```

## Code: snapshot.py (`mode=pgdump`)

```python
def _snapshot_via_pgdump(tenant_slug: str, db_name: str) -> str:
    pg_app = os.environ.get('PGBACKREST_SSH_APP', 'odoo-saas-postgres')
    # The wrapper script lives in the postgres image and uses the
    # pgbackrest IAM creds already in env there.
    remote_cmd = f'/usr/local/bin/pgdump-snapshot.sh {db_name} {tenant_slug}'
    result = subprocess.run(
        ['flyctl', 'ssh', 'console', '--app', pg_app, '--command', remote_cmd],
        check=True, capture_output=True, text=True, timeout=30 * 60,
    )
    # Wrapper prints `SNAPSHOT_KEY=<s3-key>` to stdout.
    for line in reversed(result.stdout.splitlines()):
        if line.startswith('SNAPSHOT_KEY='):
            return line.split('=', 1)[1].strip()
    raise SnapshotError(f'pgdump produced no SNAPSHOT_KEY; tail={result.stdout[-2000:]}')
```

Branch added to `take_snapshot()`:

```python
if mode == 'pgdump':
    snapshot_id = _snapshot_via_pgdump(tenant_slug, db_name)
    return SnapshotResult(snapshot_id=snapshot_id, elapsed_seconds=time.monotonic() - started)
```

## Code: rollback.py (pgdump branch)

```python
def run(plan, ...):
    ...
    if plan.snapshot_id.startswith('pgdump/'):
        return _rollback_via_pgrestore(plan, dry_run)
    # ... existing pgbackrest non-sentinel + sentinel paths stay
```

```python
def _rollback_via_pgrestore(plan, dry_run):
    pg_app = os.environ.get('PGBACKREST_SSH_APP', 'odoo-saas-postgres')
    remote_cmd = f'/usr/local/bin/pgrestore-snapshot.sh {plan.snapshot_id} {plan.tenant_db_name}'
    argv = ['flyctl', 'ssh', 'console', '--app', pg_app, '--command', remote_cmd]
    if dry_run:
        logger.info('PGBACKREST_DRY_RUN=true; skipping. Would have run: %s', ' '.join(argv))
        return RollbackResult(job_id=plan.job_id, snapshot_id=plan.snapshot_id, status='ok')
    subprocess.run(argv, check=True, capture_output=True, text=True, timeout=2 * 60 * 60)
    return RollbackResult(job_id=plan.job_id, snapshot_id=plan.snapshot_id, status='ok')
```

`pg_restore --clean --if-exists` semantics: drops + recreates each
object in the target DB before loading. This makes the tenant DB
match the dump exactly, undoing any rows + schema changes since the
snapshot — without touching any other tenant DB on the cluster.
That's the per-tenant isolation property we needed.

## Wrapper scripts (in postgres image)

`pgdump-snapshot.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
DB_NAME="$1"
TENANT_SLUG="$2"
BUCKET="${PGBACKREST_REPO1_S3_BUCKET:?}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
KEY="pgdump/${TENANT_SLUG}/${TS}.dump"

# Stream pg_dump → s3. AWS creds picked up from the pgbackrest env.
export AWS_ACCESS_KEY_ID="${PGBACKREST_REPO1_S3_KEY:?}"
export AWS_SECRET_ACCESS_KEY="${PGBACKREST_REPO1_S3_KEY_SECRET:?}"
export AWS_DEFAULT_REGION="${PGBACKREST_REPO1_S3_REGION:?}"

gosu postgres pg_dump -Fc -d "$DB_NAME" \
  | aws s3 cp - "s3://${BUCKET}/${KEY}" --no-progress

echo "SNAPSHOT_KEY=${KEY}"
```

`pgrestore-snapshot.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
KEY="$1"          # pgdump/<slug>/<ts>.dump
DB_NAME="$2"
BUCKET="${PGBACKREST_REPO1_S3_BUCKET:?}"

export AWS_ACCESS_KEY_ID="${PGBACKREST_REPO1_S3_KEY:?}"
export AWS_SECRET_ACCESS_KEY="${PGBACKREST_REPO1_S3_KEY_SECRET:?}"
export AWS_DEFAULT_REGION="${PGBACKREST_REPO1_S3_REGION:?}"

aws s3 cp "s3://${BUCKET}/${KEY}" - \
  | gosu postgres pg_restore --clean --if-exists --no-owner --no-acl -d "$DB_NAME"
```

## Caveats accepted

- **pg_dump takes locks during dump.** Acceptable for migrations
  which are operator-initiated maintenance windows anyway. Schema
  changes during dump are gated by Odoo migration window.
- **Logical dump only — no arbitrary PITR.** The pgdump snapshot
  captures the tenant at the moment the snapshot ran (immediately
  before each migration). Arbitrary point-in-time recovery between
  snapshots is not possible. For that case, the cluster pgbackrest
  WAL replay path remains available (operator override).
- **Dump size scales with tenant.** Compressed pg_dump is ~30% of
  uncompressed size. For a 100MB tenant, ~30MB per snapshot. At one
  snapshot per migration, S3 storage cost is negligible (<$1/mo per
  tenant at 30-day retention).

## Rollout

1. Land code + wrapper scripts (this design's PR).
2. Build + deploy new postgres image to staging-of-the-moment (the
   prod cluster — there's no staging Postgres yet; Item 1 covers
   that). The image change is additive (new files only) — backwards
   compatible.
3. Build + deploy new migration-runner image (already has parser fix
   from PR #120).
4. Flip migration-runner env: `SNAPSHOT_MODE=pgdump` (replacing
   `ssh`).
5. **Acceptance drill** (Tier 5 Item 2 acceptance from
   `2026-05-16-promote-to-prod-design.md`): promote tenant1+tenant2
   → new SHA. Verify both tenants migrate, both have pgdump snapshot
   keys. Rollback ONLY tenant1 via rollback-prod with restore_data=
   true. Verify tenant1's data reverted, tenant2's data intact.

## Backwards compatibility

- Existing rows with pgbackrest labels (`20260524-065900F_...`):
  rollback.run() takes the existing pgbackrest path. No code change
  needed for them.
- Existing rows with sentinels (`no-snapshot-*`): rollback.run()
  takes existing PITR path. No change needed.
- New rows from this design: snapshot_id starts with `pgdump/`,
  rollback.run() takes new pgrestore path.

Three coexisting paths, all in `rollback.run()`, dispatched by
prefix. No migration of historical rows.

## Test plan

| Suite | Cases |
|---|---|
| `test_snapshot_pgdump.py` (new) | wrapper invocation argv shape; SNAPSHOT_KEY parser; error if wrapper missing line; mock subprocess for both success + non-zero exit |
| `test_rollback_run.py` (extend) | pgdump-prefix branch; correct restore argv (`pgrestore-snapshot.sh <key> <db>`); dry-run short-circuits before invocation; non-dry-run invokes; finalize still writes audit row |
| `test_rollback_cli.py` (extend) | end-to-end: row with pgdump key → CLI invokes the right branch + finalizes |

## Open follow-ups

- **Item 1 (staging real-restore drill):** wrapper scripts + image
  changes need testing against a non-prod cluster before the
  cluster-wide `aws s3 cp` chain is exercised in prod context. The
  existing runbook at
  [`infra/runbooks/staging-pgbackrest-restore-drill.md`](../../../infra/runbooks/staging-pgbackrest-restore-drill.md)
  extends to cover this: stand up `odoo-saas-postgres-staging`,
  seed `acmesas-test`, drill `pgdump` snapshot + `pgrestore`
  rollback there. This validates Option B without risking prod.
- **Two-tenant Acceptance drill** (above §Rollout step 5) cannot
  fire until at least two active tenants exist in the canary wave.
  Today only `acmesas2` is active. Need a synthetic `acmesas3` or
  promote-of-an-existing-tenant to canary first.
