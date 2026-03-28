#!/bin/bash
set -e

# Railway PostgreSQL provides these environment variables:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE
# Map them to Odoo CLI arguments.

DB_HOST="${PGHOST:-db}"
DB_PORT="${PGPORT:-5432}"
DB_USER="${PGUSER:-odoo}"
DB_PASSWORD="${PGPASSWORD:-odoo}"
DB_NAME="${PGDATABASE:-odoo}"

# Railway provides PORT for the web server
WEB_PORT="${PORT:-8069}"

# On first run, initialize the database with base module
# INIT_MODULES can be set via env var (e.g., "base,web,contacts")
INIT_MODULES="${INIT_MODULES:-}"

INIT_FLAG=""
if [ -n "$INIT_MODULES" ]; then
    INIT_FLAG="--init=$INIT_MODULES"
fi

# UPDATE_MODULES: comma-separated list of modules to update (e.g., "account,sale")
UPDATE_MODULES="${UPDATE_MODULES:-}"
UPDATE_FLAG=""
if [ -n "$UPDATE_MODULES" ]; then
    UPDATE_FLAG="--update=$UPDATE_MODULES"
fi

# RESET_DB: set to "1" to drop and recreate the database (for major version upgrades)
if [ "${RESET_DB:-}" = "1" ]; then
    echo "RESET_DB=1 — Dropping and recreating database '$DB_NAME'..."
    export PGPASSWORD="$DB_PASSWORD"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" 2>/dev/null || true
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" 2>/dev/null || true
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\" ENCODING 'UTF8';" 2>/dev/null || true
    echo "Database '$DB_NAME' recreated."
    # Auto-init base after reset
    if [ -z "$INIT_MODULES" ] || [ "$INIT_MODULES" = "x" ]; then
        INIT_MODULES="base"
    fi
fi

# STOP_AFTER_INIT: set to "1" to exit after init/update (useful for one-shot migrations)
STOP_FLAG=""
if [ "${STOP_AFTER_INIT:-}" = "1" ]; then
    STOP_FLAG="--stop-after-init"
fi

exec /odoo/odoo-bin \
    --config=/etc/odoo/odoo.conf \
    --db_host="$DB_HOST" \
    --db_port="$DB_PORT" \
    --db_user="$DB_USER" \
    --db_password="$DB_PASSWORD" \
    --database="$DB_NAME" \
    --http-port="$WEB_PORT" \
    --proxy-mode \
    --no-database-list \
    --db-filter="^${DB_NAME}$" \
    $INIT_FLAG \
    $UPDATE_FLAG \
    $STOP_FLAG \
    "$@"
