#!/usr/bin/env bash
# Phase 4.1 v0.4 — operator license CLI.
#
# Thin curl wrapper around the /api/internal/license/{issue,revoke,list}
# HMAC-gated endpoints on the control plane. Stays in bash so it has zero
# install footprint on a fresh laptop — every dependency (curl, openssl,
# jq, date) is in macOS + Linux base images.
#
# Required env:
#   SAAS_PROVISIONING_SECRET — shared HMAC secret (same value Vercel has).
#   LICENSE_AUTHORITY_URL    — base URL of the admin app, e.g.
#                              https://admin.goliatt.co
#
# Usage:
#   ./infra/scripts/license-cli.sh issue \
#       <customer_ref> <image_sha256> [<term_days> [<grace_days> [<notes>]]]
#   ./infra/scripts/license-cli.sh revoke <license_id> "<reason>"
#   ./infra/scripts/license-cli.sh list-by-customer <customer_ref>
#   ./infra/scripts/license-cli.sh list-by-image <image_sha256>
#
# All responses are pretty-printed via jq if available; falls back to
# raw JSON otherwise. Non-zero exit on HTTP 4xx/5xx.

set -euo pipefail

# Defer the env-var check until we know the subcommand actually makes a
# network call — `help` doesn't, so it shouldn't require any creds.
require_env() {
    if [ -z "${SAAS_PROVISIONING_SECRET:-}" ] || [ -z "${LICENSE_AUTHORITY_URL:-}" ]; then
        echo "ERROR: SAAS_PROVISIONING_SECRET and LICENSE_AUTHORITY_URL must be set" >&2
        exit 2
    fi
}

BASE_URL="${LICENSE_AUTHORITY_URL%/}"
HAS_JQ=0
command -v jq >/dev/null 2>&1 && HAS_JQ=1

pretty() {
    if [ "$HAS_JQ" = 1 ]; then jq .; else cat; fi
}

# Build HMAC envelope and POST. Args: <path> <body>.
post_signed() {
    require_env
    local path="$1"
    local body="$2"
    local ts
    ts=$(date +%s)
    # Linux openssl emits "(stdin)= <hex>"; macOS emits raw hex. -hmac with -hex
    # is portable but the output format differs — strip "(stdin)= " if present.
    local sig
    sig=$(printf '%s.%s' "$ts" "$body" \
        | openssl dgst -sha256 -hmac "$SAAS_PROVISIONING_SECRET" -hex \
        | awk '{print $NF}')
    local url="${BASE_URL}${path}"
    # -w writes status to stderr-bound file via a tempfile trick so we can
    # both print the body AND inspect the status code.
    local tmp
    tmp=$(mktemp)
    local status
    status=$(curl -sS -X POST "$url" \
        -H "content-type: application/json" \
        -H "x-saas-signature: sha256=${sig}" \
        -H "x-saas-timestamp: ${ts}" \
        --data-binary "$body" \
        -o "$tmp" \
        -w "%{http_code}")
    cat "$tmp" | pretty
    rm -f "$tmp"
    if [ "$status" -ge 400 ]; then
        echo "" >&2
        echo "HTTP $status from $path" >&2
        exit 1
    fi
}

cmd=${1:-help}
shift || true

case "$cmd" in
    issue)
        if [ "$#" -lt 2 ]; then
            echo "Usage: $0 issue <customer_ref> <image_sha256> [<term_days> [<grace_days> [<notes>]]]" >&2
            exit 2
        fi
        customer_ref="$1"
        image_sha="$2"
        term_days="${3:-365}"
        grace_days="${4:-14}"
        notes="${5:-}"
        body=$(printf '{"customer_ref":"%s","image_sha256":"%s","term_days":%d,"grace_days":%d' \
            "$customer_ref" "$image_sha" "$term_days" "$grace_days")
        if [ -n "$notes" ]; then
            body="${body},\"notes\":\"${notes}\""
        fi
        body="${body}}"
        post_signed "/api/internal/license/issue" "$body"
        ;;
    revoke)
        if [ "$#" -lt 2 ]; then
            echo "Usage: $0 revoke <license_id> '<reason>'" >&2
            exit 2
        fi
        license_id="$1"
        reason="$2"
        body=$(printf '{"license_id":"%s","reason":"%s"}' "$license_id" "$reason")
        post_signed "/api/internal/license/revoke" "$body"
        ;;
    list-by-customer)
        if [ "$#" -lt 1 ]; then
            echo "Usage: $0 list-by-customer <customer_ref>" >&2
            exit 2
        fi
        body=$(printf '{"customer_ref":"%s"}' "$1")
        post_signed "/api/internal/license/list" "$body"
        ;;
    list-by-image)
        if [ "$#" -lt 1 ]; then
            echo "Usage: $0 list-by-image <image_sha256>" >&2
            exit 2
        fi
        body=$(printf '{"image_sha256":"%s"}' "$1")
        post_signed "/api/internal/license/list" "$body"
        ;;
    help|-h|--help|"")
        cat <<EOF
license-cli.sh — operator CLI for the Phase 4.1 license authority

Commands:
  issue <customer_ref> <image_sha256> [<term_days> [<grace_days> [<notes>]]]
      Mint a new license. term_days defaults to 365, grace_days to 14.
      Returns the row; hand the .id to the customer out-of-band.

  revoke <license_id> '<reason>'
      Set revoked_at + revoked_reason. Customer's saas_license_gate sees
      this on its next hourly tick.

  list-by-customer <customer_ref>
      List up to 100 licenses for this customer, newest first.

  list-by-image <image_sha256>
      List up to 100 licenses bound to this image digest.

Required env:
  SAAS_PROVISIONING_SECRET   shared HMAC secret
  LICENSE_AUTHORITY_URL      e.g. https://admin.goliatt.co

Examples:
  ./infra/scripts/license-cli.sh issue acme@example.com \\
      1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef \\
      365 14 "Q2 2026 enterprise renewal"

  ./infra/scripts/license-cli.sh revoke \\
      a1b2c3d4-e5f6-7890-1234-567890abcdef \\
      "Non-payment, 90 days past due"

  ./infra/scripts/license-cli.sh list-by-customer acme@example.com
EOF
        ;;
    *)
        echo "Unknown command: $cmd" >&2
        exit 2
        ;;
esac
