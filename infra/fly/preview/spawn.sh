#!/bin/bash
# spawn.sh — provision a new preview env for a spec.
#
# Usage:
#   spawn.sh <spec_id> <image_ref>
#
# Where:
#   spec_id   — the GitHub issue/PR number (positive integer)
#   image_ref — the OCI image to deploy (e.g. ghcr.io/<org>/odoo-saas:<branch-sha>)
#
# Effects:
#   - Creates Fly app `odoo-saas-preview-spec-<spec_id>`
#   - Creates paired Fly Postgres app
#   - Sets secrets
#   - Restores masked snapshot via seed.sh
#   - Creates reviewer login via make-reviewer.sh
#   - Prints JSON: { "url": ..., "login": ..., "password": ... }

set -euo pipefail

SPEC_ID="${1:?spec_id required}"
IMAGE_REF="${2:?image_ref required}"
ORG="${FLY_ORG:-odoo-saas}"
REGION="${FLY_REGION:-iad}"
SIZE="${FLY_SIZE:-shared-cpu-1x}"
PG_SIZE="${FLY_PG_SIZE:-shared-cpu-1x}"
PG_VOLUME_GB="${FLY_PG_VOLUME_GB:-5}"

APP_NAME="odoo-saas-preview-spec-${SPEC_ID}"
DB_APP_NAME="${APP_NAME}-db"
PREVIEW_TENANT_DB="preview_${SPEC_ID}"

log() {
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    printf '{"ts":"%s","level":"%s","msg":"%s","spec_id":"%s"}\n' \
        "$ts" "$1" "$2" "$SPEC_ID" >&2
}

# --- Validate ---
[ "$SPEC_ID" -gt 0 ] 2>/dev/null || { log error "spec_id must be a positive integer"; exit 1; }
command -v flyctl >/dev/null || { log error "flyctl not installed"; exit 1; }
command -v jq >/dev/null || { log error "jq not installed"; exit 1; }

log info "spawn.start app=$APP_NAME db=$DB_APP_NAME image=$IMAGE_REF"

# --- 1. Create the apps ---
if ! flyctl apps show "$APP_NAME" >/dev/null 2>&1; then
    log info "spawn.create_app"
    flyctl apps create "$APP_NAME" --org "$ORG"
fi

if ! flyctl apps show "$DB_APP_NAME" >/dev/null 2>&1; then
    log info "spawn.create_db_app"
    flyctl postgres create \
        --name "$DB_APP_NAME" \
        --org "$ORG" \
        --region "$REGION" \
        --initial-cluster-size 1 \
        --vm-size "$PG_SIZE" \
        --volume-size "$PG_VOLUME_GB" \
        --no-prompt
fi

# --- 2. Attach the DB ---
log info "spawn.attach_db"
flyctl postgres attach "$DB_APP_NAME" \
    --app "$APP_NAME" \
    --database-name "$PREVIEW_TENANT_DB" \
    --variable-name DATABASE_URL 2>/dev/null || true

# --- 3. Set secrets ---
log info "spawn.set_secrets"
ADMIN_PASSWORD=$(openssl rand -base64 32)
flyctl secrets set \
    --app "$APP_NAME" \
    --stage \
    ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    PLATFORM="preview" \
    PORT="8069"

# --- 4. Deploy the image ---
log info "spawn.deploy image=$IMAGE_REF"
flyctl deploy \
    --app "$APP_NAME" \
    --image "$IMAGE_REF" \
    --strategy immediate \
    --wait-timeout 600

# --- 5. Seed with masked data ---
log info "spawn.seed"
"$(dirname "$0")/seed.sh" "$SPEC_ID"

# --- 6. Create reviewer login ---
log info "spawn.make_reviewer"
REVIEWER_JSON=$("$(dirname "$0")/make-reviewer.sh" "$SPEC_ID" "$ADMIN_PASSWORD")

# --- 7. Emit final URL + creds JSON ---
URL="https://preview-${SPEC_ID}.${PREVIEW_DOMAIN:-your-domain.example.com}"

log info "spawn.done url=$URL"

jq -n \
    --arg url "$URL" \
    --arg app_name "$APP_NAME" \
    --arg db_app_name "$DB_APP_NAME" \
    --arg tenant_db "$PREVIEW_TENANT_DB" \
    --argjson reviewer "$REVIEWER_JSON" \
    '{
        "url": $url,
        "app_name": $app_name,
        "db_app_name": $db_app_name,
        "tenant_db": $tenant_db,
        "reviewer": $reviewer
    }'
