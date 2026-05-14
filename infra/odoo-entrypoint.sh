#!/bin/bash
# infra/odoo-entrypoint.sh — platform-agnostic Odoo 19 multi-tenant entrypoint.
#
# Boots Odoo with dbfilter=^%d$ so each request is routed to the database whose
# name matches the request subdomain (or X-Odoo-Database header). There is no
# single hardcoded tenant DB. Database creation/drop is handled by the SaaS
# control plane via /web/database/*, gated by ADMIN_PASSWORD and a Traefik
# IP-allowlist (configured at the proxy, not here).
#
# Required env:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD  — Postgres connection (used to bootstrap
#                                          connections + create new tenant DBs)
#   ADMIN_PASSWORD                       — Odoo master password for /web/database/*
#
# Optional env:
#   PORT                — HTTP port (default 8069)
#   PLATFORM            — railway|fly|compose; echoed at startup, reserved for
#                          platform-conditional behavior (none today)
#   WORKERS             — overrides workers count from config (optional)
#
# Maintenance mode (one-shot operations against a specific DB):
#   TARGET_DB           — name of the DB to operate on (required for the below)
#   INIT_MODULES        — comma-separated modules to install (-i)
#   UPDATE_MODULES      — comma-separated modules to update (-u)
#   RESET_DB=1          — drop + recreate TARGET_DB before running -i
#   STOP_AFTER_INIT=1   — exit after init/update completes
#
# In normal (multi-tenant serving) mode none of the maintenance env vars are
# set; the entrypoint just launches the Odoo HTTP server with dbfilter=^%d$.

set -euo pipefail

# --- Privilege drop ----------------------------------------------------------
# We start as root so we can fix ownership of the data volume (Railway / Fly
# mount volumes root-owned, but Odoo runs as uid 1000 and must write its
# data_dir). After the chown we re-exec ourselves as `odoo` via gosu. If
# already non-root (e.g. local docker-compose with `user:` set, or a platform
# that pre-chowns the mount), this block is a no-op.
if [ "$(id -u)" = "0" ]; then
    ODOO_DATA_DIR="${ODOO_DATA_DIR:-/var/lib/odoo}"
    mkdir -p "$ODOO_DATA_DIR"
    chown -R odoo:odoo "$ODOO_DATA_DIR"
    exec gosu odoo "$0" "$@"
fi

# --- Required env validation -------------------------------------------------

if [ -z "${ADMIN_PASSWORD:-}" ]; then
    echo "FATAL: ADMIN_PASSWORD is required. Set it in the environment." >&2
    echo "       Generate one with: openssl rand -base64 32" >&2
    exit 1
fi

# --- Connection settings -----------------------------------------------------

DB_HOST="${PGHOST:-db}"
DB_PORT="${PGPORT:-5432}"
DB_USER="${PGUSER:-odoo}"
DB_PASSWORD="${PGPASSWORD:-}"
WEB_PORT="${PORT:-8069}"

if [ -z "$DB_PASSWORD" ]; then
    echo "FATAL: PGPASSWORD is required." >&2
    exit 1
fi

# --- Platform diagnostics ----------------------------------------------------

echo "odoo-entrypoint: PLATFORM=${PLATFORM:-<unset>} HOST=${DB_HOST}:${DB_PORT} USER=${DB_USER}"

# --- Runtime config: inject ADMIN_PASSWORD ----------------------------------
# admin_passwd is a FileOnlyOption in Odoo 19 (odoo/tools/config.py:207) — it
# cannot be set via CLI. We compose a runtime config that includes the baked
# /etc/odoo/odoo.conf plus the runtime-injected admin password. Odoo hashes
# the plaintext on first verification (passlib verify_and_update).
RUNTIME_CONF=/tmp/odoo-runtime.conf
{
    cat /etc/odoo/odoo.conf
    echo ""
    echo "admin_passwd = ${ADMIN_PASSWORD}"
} > "$RUNTIME_CONF"
chmod 600 "$RUNTIME_CONF"

# --- Maintenance ops (single-target) -----------------------------------------

TARGET_DB="${TARGET_DB:-}"
INIT_MODULES="${INIT_MODULES:-}"
UPDATE_MODULES="${UPDATE_MODULES:-}"
RESET_DB="${RESET_DB:-}"
STOP_AFTER_INIT="${STOP_AFTER_INIT:-}"

MAINTENANCE_MODE=0
if [ -n "$INIT_MODULES" ] || [ -n "$UPDATE_MODULES" ] || [ "$RESET_DB" = "1" ]; then
    MAINTENANCE_MODE=1
    if [ -z "$TARGET_DB" ]; then
        echo "FATAL: maintenance ops (INIT_MODULES/UPDATE_MODULES/RESET_DB) require TARGET_DB." >&2
        exit 1
    fi
fi

if [ "$RESET_DB" = "1" ]; then
    echo "RESET_DB=1 — dropping and recreating database '$TARGET_DB'..."
    export PGPASSWORD="$DB_PASSWORD"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$TARGET_DB' AND pid <> pg_backend_pid();" 2>/dev/null || true
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS \"$TARGET_DB\";"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "CREATE DATABASE \"$TARGET_DB\" OWNER \"$DB_USER\" ENCODING 'UTF8';"
    echo "Database '$TARGET_DB' recreated."
    if [ -z "$INIT_MODULES" ]; then
        INIT_MODULES="base"
    fi
fi

# --- Argument assembly -------------------------------------------------------

ARGS=(
    --config="$RUNTIME_CONF"
    --db_host="$DB_HOST"
    --db_port="$DB_PORT"
    --db_user="$DB_USER"
    --db_password="$DB_PASSWORD"
    --http-port="$WEB_PORT"
    --proxy-mode
)

# Routing mode selection:
#   SINGLE_DB=<name>   → single-DB serving mode for the operator Odoo or
#                       any other single-tenant Odoo. dbfilter pinned to
#                       ^<name>$ so the server only ever resolves to that
#                       one DB regardless of the request Host header.
#                       Use this when the app fronts ONE database with
#                       a stable hostname.
#   (otherwise)         → multi-tenant SaaS mode (default). dbfilter
#                       ^%d$ resolves the DB name from the request
#                       subdomain; the control plane provisions and
#                       routes tenant subdomains.
SINGLE_DB="${SINGLE_DB:-}"
if [ -n "$SINGLE_DB" ]; then
    ARGS+=(--database="$SINGLE_DB" --db-filter="^${SINGLE_DB}\$")
    echo "odoo-entrypoint: SINGLE_DB mode — pinned to database '$SINGLE_DB'"
else
    ARGS+=(--db-filter='^%d$')
fi

if [ -n "${WORKERS:-}" ]; then
    ARGS+=(--workers="$WORKERS")
fi

if [ "$MAINTENANCE_MODE" = "1" ]; then
    ARGS+=(--database="$TARGET_DB")
    [ -n "$INIT_MODULES" ]   && ARGS+=(--init="$INIT_MODULES")
    [ -n "$UPDATE_MODULES" ] && ARGS+=(--update="$UPDATE_MODULES")
    [ "$STOP_AFTER_INIT" = "1" ] && ARGS+=(--stop-after-init)
    echo "Maintenance run against TARGET_DB=$TARGET_DB"
fi

exec /odoo/odoo-bin "${ARGS[@]}" "$@"
