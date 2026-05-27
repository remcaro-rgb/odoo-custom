#!/usr/bin/env bash
# Per-tenant rollback companion to pgdump-snapshot.sh.
#
# Reads the named pgdump key from S3 and replays it into the tenant's
# database via `pg_restore --clean --if-exists`. Other tenant DBs on
# the same cluster are untouched — that's the per-tenant isolation
# property we wanted from Tier 5 Item 2.
#
# Invoked by migration_runner.rollback.run() over flyctl-ssh when the
# snapshot_id starts with `pgdump/`.
#
# Spec: docs/superpowers/specs/2026-05-27-per-tenant-restore-design.md
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "usage: $0 <s3_key> <db_name>" >&2
    exit 2
fi
KEY="$1"              # e.g. pgdump/acmesas2/20260527T120000Z.dump
DB_NAME="$2"

BUCKET="${PGBACKREST_REPO1_S3_BUCKET:?PGBACKREST_REPO1_S3_BUCKET unset}"

export AWS_ACCESS_KEY_ID="${PGBACKREST_REPO1_S3_KEY:?}"
export AWS_SECRET_ACCESS_KEY="${PGBACKREST_REPO1_S3_KEY_SECRET:?}"
export AWS_DEFAULT_REGION="${PGBACKREST_REPO1_S3_REGION:?}"

# Stream s3 → pg_restore. --clean --if-exists makes the restore
# idempotent against the current state of the tenant DB: each object
# in the dump is dropped (if present) and re-created. --no-owner and
# --no-acl skip role/grant statements the dump may carry (Odoo
# tenants live under a shared role; we don't want to thrash grants).
aws s3 cp "s3://${BUCKET}/${KEY}" - --no-progress \
    | gosu postgres pg_restore \
        --clean --if-exists --no-owner --no-acl \
        -d "$DB_NAME"
