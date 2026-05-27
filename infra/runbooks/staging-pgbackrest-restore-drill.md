# Staging pgbackrest real-restore drill

How to prove the full pgbackrest restore path end-to-end against a
non-production Postgres — pre-condition for ever flipping
`PGBACKREST_DRY_RUN=false` on the prod migration-runner.

Pairs with Tier 5 Item 1 of
[`docs/superpowers/specs/2026-05-16-promote-to-prod-design.md`](../../docs/superpowers/specs/2026-05-16-promote-to-prod-design.md).
**Operator-owned drill** — does not run on a schedule.

## Why this exists

`odoo-saas-postgres` runs **one cluster, one stanza, shared tenants**.
A `pgbackrest restore` stops Postgres + replays WAL into the data dir
→ wipes every tenant on the cluster, not just the one being rolled
back. We can't fire the real path in prod, so this runbook stands up
a throwaway Postgres + tenant and drills there.

## Prereqs (operator fills these in before running)

| Item | Where it comes from | This drill's value |
|---|---|---|
| Staging Postgres Fly app name | Operator decision — recommend `odoo-saas-postgres-staging` | _TBD_ |
| pgbackrest S3 prefix | Operator decision — recommend `staging/` subpath of existing bucket, OR a separate bucket if blast-radius is a concern | _TBD_ |
| Synthetic tenant slug | Operator decision — recommend `acmesas-test` | _TBD_ |
| FLY_SSH_TOKEN_POSTGRES_STAGING | New Fly token, ssh scope on the staging Postgres app only | _TBD_ |

## Steps

### 1. Stand up the staging Postgres

```bash
# From repo root
APP=odoo-saas-postgres-staging   # ← operator choice
S3_PREFIX=staging                # ← operator choice

flyctl apps create "$APP"

# Mirror the prod fly.toml, override app + S3 prefix
cp infra/fly/postgres/fly.toml /tmp/staging-fly.toml
sed -i '' "s/^app *= *\"odoo-saas-postgres\"/app = \"$APP\"/" /tmp/staging-fly.toml

# Same secrets as prod EXCEPT a distinct PGBACKREST_REPO1_S3_BUCKET-prefix
flyctl secrets set --app "$APP" \
  POSTGRES_PASSWORD="<from prod secret manager>" \
  PGBACKREST_REPO1_S3_BUCKET="<prod-bucket>" \
  PGBACKREST_REPO1_S3_REGION="<prod-region>" \
  PGBACKREST_REPO1_S3_KEY="<prod-iam-key>" \
  PGBACKREST_REPO1_S3_KEY_SECRET="<prod-iam-secret>" \
  PGBACKREST_REPO1_CIPHER_PASS="<distinct-cipher-pass>" \
  PGBACKREST_REPO1_PATH="/$S3_PREFIX/shared"   # isolate from prod stanza

flyctl volumes create pgdata --app "$APP" --size 10 --region iad

flyctl deploy --app "$APP" --config /tmp/staging-fly.toml \
  --dockerfile infra/postgres/Dockerfile --remote-only
```

### 2. Seed a synthetic tenant with a full backup history

```bash
SLUG=acmesas-test                # ← operator choice

# Provision the tenant DB via the gateway against staging
PROVISIONING_URL="https://<staging-odoo>/saas/provision" \
PROVISIONING_SECRET="<hmac-secret>" \
  ./scripts/provision-tenant.sh "$SLUG"  # uses existing gateway

# Take a full backup so we have a real label to restore to
flyctl ssh console --app "$APP" -C \
  "gosu postgres pgbackrest --stanza=shared --type=full backup"

# Insert a marker row we can check is GONE after rollback
flyctl ssh console --app "$APP" -C \
  "gosu postgres psql -d $SLUG -c \"
    CREATE TABLE IF NOT EXISTS rollback_canary (id serial, marker text, created timestamptz default now());
    INSERT INTO rollback_canary (marker) VALUES ('pre-migration');
  \""

# Wait for the WAL containing that insert to archive
flyctl ssh console --app "$APP" -C \
  "gosu postgres pgbackrest --stanza=shared check"
```

### 3. Stage the migration-runner to target staging

```bash
flyctl secrets set --app odoo-saas-migration-runner \
  PGBACKREST_SSH_APP="$APP" \
  PGBACKREST_DRY_RUN=false \
  FLY_API_TOKEN="<staging-ssh-token>"  # FLY_SSH_TOKEN_POSTGRES_STAGING
```

This **also retargets prod-day rollbacks at the staging cluster** — so
only do this when you're actively drilling, and reverse it in step 6.

### 4. Insert a destructive change on the tenant after the snapshot

```bash
flyctl ssh console --app "$APP" -C \
  "gosu postgres psql -d $SLUG -c \"
    INSERT INTO rollback_canary (marker) VALUES ('post-migration-WILL-BE-GONE');
    SELECT * FROM rollback_canary;
  \""
```

Note the timestamp — this is what we want gone after the restore.

### 5. Fire rollback via the migration-runner SSH chain

```bash
JOB_ID="<uuid-of-a-test-row-in-tenant_migration_jobs>"
PREV_SHA="<sha-the-rollback-target>"

flyctl ssh console --app odoo-saas-migration-runner -C \
  "python -m migration_runner.rollback $JOB_ID $PREV_SHA"
```

Expected log lines:
- `rollback start job=<uuid> tenant=acmesas-test snapshot=<real-label> dry_run=False`
- `pgbackrest info` succeeds (real S3 catalog hit)
- `restore` exits 0
- `rollback complete job=<uuid> dry_run=False`

### 6. Verify the rollback actually moved data

```bash
flyctl ssh console --app "$APP" -C \
  "gosu postgres psql -d $SLUG -c \"SELECT * FROM rollback_canary;\""
```

**Expected:** only the `pre-migration` row. The
`post-migration-WILL-BE-GONE` row is absent. If both rows are still
present, pgbackrest did not actually restore — investigate.

Also confirm in the control-plane Neon DB:

```bash
psql "$CONTROL_PLANE_PG_DSN" -c "
  SELECT slug, last_migrated_sha
    FROM tenants WHERE slug = '$SLUG';"
```

The `last_migrated_sha` should match `$PREV_SHA`.

### 7. Flip the migration-runner back to prod safety

```bash
flyctl secrets set --app odoo-saas-migration-runner \
  PGBACKREST_SSH_APP=odoo-saas-postgres \
  PGBACKREST_DRY_RUN=true
flyctl secrets set --app odoo-saas-migration-runner \
  FLY_API_TOKEN="<prod-postgres-ssh-token>"  # FLY_SSH_TOKEN_POSTGRES
```

**Required** before any prod rollback fires again. Leaving the staging
target wired would make the next prod rollback no-op (wrong cluster).

### 8. Tear down (optional)

If the staging cluster was only stood up for this drill:

```bash
flyctl apps destroy "$APP" --yes
# Don't auto-delete the S3 backups — keep them for forensic review of
# the drill. Manual cleanup later via aws cli on the prefix.
```

## What this drill proves (and what it does not)

**Proves:**
- `_pgbackrest_argv`'s `--set <label> --delta restore` actually works
  when `dry_run=false`.
- The S3 catalog write + read path is healthy end-to-end.
- The control-plane audit row + sha revert happen atomically.

**Does NOT prove:**
- Per-tenant restore on a shared cluster (that's Item 2 — selectivity).
  This drill restores the whole staging cluster, which works because
  the staging cluster has exactly one tenant.
- Production cluster behavior under load (staging is a quiet sandbox).

## Reference good outcomes

- Drill ID: _TBD — fill in after first successful run_
- pgbackrest label restored: _TBD_
- Restore wall-clock duration: _TBD_
