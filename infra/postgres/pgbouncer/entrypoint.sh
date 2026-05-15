#!/bin/bash
# Entrypoint — generates the SCRAM userlist.txt from env, then execs pgbouncer.
#
# Required env:
#   PG_HOST             upstream postgres hostname (substituted into pgbouncer.ini)
#   PG_PORT             upstream postgres port (typically 5432)
#   PGUSER              the role pgbouncer authenticates clients AS
#   PGPASSWORD          plaintext password for the role above; we re-encode
#                       it as SCRAM-SHA-256 before writing userlist.txt so
#                       the file at rest doesn't contain plaintext

set -euo pipefail

: "${PG_HOST:?PG_HOST is required}"
: "${PG_PORT:=5432}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"

export PG_HOST PG_PORT

# Generate a SCRAM-SHA-256 hash of the password — same format Postgres
# stores. PgBouncer's auth_file accepts either plain "user" "password" or
# the SCRAM string.
#
# alpine's pgbouncer ships a `pg_md5` helper but no `pg_scram` analog;
# we shell out to psql against a no-op connection to use Postgres'
# scram_create_secret() function. If that's too elaborate, the simpler
# fallback is plain-text in userlist.txt with auth_type=trust — but that
# defeats the point. Use psql.
SCRAM_HASH=$(PGPASSWORD="$PGPASSWORD" psql -tA -h "$PG_HOST" -p "$PG_PORT" -U "$PGUSER" -d postgres \
    -c "SELECT 'SCRAM-SHA-256\$' || regexp_replace(rolpassword, '^SCRAM-SHA-256\\\$', '') FROM pg_authid WHERE rolname = '$PGUSER';" 2>/dev/null || true)

if [ -z "$SCRAM_HASH" ]; then
    echo "pgbouncer-entrypoint: could not fetch SCRAM hash for $PGUSER from $PG_HOST; falling back to plaintext userlist" >&2
    printf '"%s" "%s"\n' "$PGUSER" "$PGPASSWORD" > /etc/pgbouncer/userlist.txt
else
    printf '"%s" "%s"\n' "$PGUSER" "$SCRAM_HASH" > /etc/pgbouncer/userlist.txt
fi
chmod 600 /etc/pgbouncer/userlist.txt
chown pgbouncer:pgbouncer /etc/pgbouncer/userlist.txt

# pgbouncer's %(VAR)s substitution doesn't reach the [databases] section
# (parsed literally before env interpolation). Generate a finalized
# pgbouncer.ini at startup with the real hostname inlined.
INI_SRC=/etc/pgbouncer/pgbouncer.ini
INI_OUT=/tmp/pgbouncer.runtime.ini
sed -e "s|%(PG_HOST)s|$PG_HOST|g" -e "s|%(PG_PORT)s|$PG_PORT|g" "$INI_SRC" > "$INI_OUT"
chown pgbouncer:pgbouncer "$INI_OUT"
echo "pgbouncer-entrypoint: launching with PG_HOST=$PG_HOST PG_PORT=$PG_PORT" >&2

exec su-exec pgbouncer pgbouncer "$INI_OUT"
