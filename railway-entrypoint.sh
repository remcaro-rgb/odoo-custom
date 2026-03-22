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
    "$@"
