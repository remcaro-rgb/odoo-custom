#!/bin/bash
# init-pgbackrest.sh — one-shot stanza creation on first Postgres boot.
#
# Dropped into /docker-entrypoint-initdb.d/ by the Dockerfile. The official
# postgres image runs scripts in that directory exactly once, after initdb,
# while still in single-user mode bootstrap. By the time this runs the
# cluster has initialized PGDATA and we have a postgres role available.
#
# Skips silently if PGBACKREST_REPO1_S3_BUCKET is not set (local dev /
# unconfigured environment) — the stanza will need manual creation when
# real S3 credentials are wired in.

set -euo pipefail

if [ -z "${PGBACKREST_REPO1_S3_BUCKET:-}" ]; then
    echo "init-pgbackrest: PGBACKREST_REPO1_S3_BUCKET not set — skipping stanza create."
    echo "init-pgbackrest: Run 'pgbackrest --stanza=shared stanza-create' manually once S3 creds are configured."
    exit 0
fi

echo "init-pgbackrest: creating stanza 'shared' against bucket ${PGBACKREST_REPO1_S3_BUCKET}..."
gosu postgres pgbackrest --stanza=shared --log-level-console=info stanza-create
gosu postgres pgbackrest --stanza=shared --log-level-console=info check
echo "init-pgbackrest: stanza ready."
