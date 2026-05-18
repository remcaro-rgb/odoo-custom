#!/bin/bash
# destroy.sh — tear down a preview env.
#
# Usage:  destroy.sh <spec_id>
#
# Destroys the Fly app, its paired Postgres, and any DNS records.
# Safe to call repeatedly — silently no-ops if already destroyed.

set -euo pipefail

SPEC_ID="${1:?spec_id required}"
APP_NAME="odoo-saas-preview-spec-${SPEC_ID}"
DB_APP_NAME="${APP_NAME}-db"

log() {
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    printf '{"ts":"%s","level":"%s","msg":"%s","spec_id":"%s"}\n' \
        "$ts" "$1" "$2" "$SPEC_ID" >&2
}

log info "destroy.start app=$APP_NAME"

if flyctl apps show "$APP_NAME" >/dev/null 2>&1; then
    flyctl apps destroy "$APP_NAME" --yes
    log info "destroy.app_destroyed"
else
    log info "destroy.app_already_gone"
fi

if flyctl apps show "$DB_APP_NAME" >/dev/null 2>&1; then
    flyctl apps destroy "$DB_APP_NAME" --yes
    log info "destroy.db_app_destroyed"
else
    log info "destroy.db_already_gone"
fi

log info "destroy.done"
