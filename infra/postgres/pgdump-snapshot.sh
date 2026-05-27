#!/usr/bin/env bash
# Per-tenant pre-migration snapshot.
#
# Streams `pg_dump -Fc` of the tenant DB straight to S3 under a
# `pgdump/<tenant>/<ts>.dump` key. Prints `SNAPSHOT_KEY=<key>` on the
# last line so the migration-runner can parse it and write it into
# `tenant_migration_jobs.snapshot_id`.
#
# Invoked by the migration-runner daemon over flyctl-ssh when
# SNAPSHOT_MODE=pgdump. AWS creds come from the pgbackrest env that's
# already present on this machine — no new IAM, no new bucket.
#
# Pairs with pgrestore-snapshot.sh for the rollback path.
# Spec: docs/superpowers/specs/2026-05-27-per-tenant-restore-design.md
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: $0 <db_name> <tenant_slug>" >&2
    exit 2
fi
DB_NAME="$1"
TENANT_SLUG="$2"

BUCKET="${PGBACKREST_REPO1_S3_BUCKET:?PGBACKREST_REPO1_S3_BUCKET unset}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
KEY="pgdump/${TENANT_SLUG}/${TS}.dump"

# AWS env from pgbackrest's existing IAM creds. Same bucket, separate
# prefix — lifecycle policy on `pgdump/*` set independently.
export AWS_ACCESS_KEY_ID="${PGBACKREST_REPO1_S3_KEY:?}"
export AWS_SECRET_ACCESS_KEY="${PGBACKREST_REPO1_S3_KEY_SECRET:?}"
export AWS_DEFAULT_REGION="${PGBACKREST_REPO1_S3_REGION:?}"

# pg_dump -Fc = custom format (compressed, suitable for pg_restore
# --clean). gosu drops to postgres for the local socket auth.
# Pipe to aws s3 cp so we never hold the dump on local disk —
# important for large tenants and read-only postgres volumes.
gosu postgres pg_dump -Fc -d "$DB_NAME" \
    | aws s3 cp - "s3://${BUCKET}/${KEY}" --no-progress >/dev/null

# Last line — the runner's _snapshot_via_pgdump parser searches for
# this exact prefix.
echo "SNAPSHOT_KEY=${KEY}"
