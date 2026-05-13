#!/usr/bin/env bash
# Adds the two DNS records that externalize the Fly Traefik tenant edge:
#   A    *.fly.app.goliatt.co → 66.241.125.94            (Fly shared v4)
#   AAAA *.fly.app.goliatt.co → 2a09:8280:1::115:5cd4:0  (Fly dedicated v6)
#
# Both proxied=false (DNS-only / grey cloud) — Traefik does its own TLS with
# the Let's Encrypt wildcard; routing through Cloudflare's proxy would
# require a Cloudflare-side cert that doesn't cover a second-level wildcard
# on the free plan.
#
# Usage:
#   CF_API_TOKEN=<your token>   ./infra/runbooks/add-fly-tenant-dns.sh
#
# The token needs "Edit zone DNS" for the goliatt.co zone — same scope as
# the CF_DNS_API_TOKEN secret already set on the odoo-saas-traefik Fly app.
# Re-running is safe: the script skips records that already exist with the
# correct value.

set -euo pipefail

: "${CF_API_TOKEN:?CF_API_TOKEN env var is required (Cloudflare API token with Zone:DNS:Edit on goliatt.co)}"

ZONE="goliatt.co"
A_V4="66.241.125.94"
AAAA_V6="2a09:8280:1::115:5cd4:0"

CF() {
    curl -sS -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" "$@"
}

echo "→ Resolve zone id for $ZONE"
ZONE_ID=$(CF "https://api.cloudflare.com/client/v4/zones?name=$ZONE" \
    | python3 -c "import json,sys;r=json.load(sys.stdin);assert r['success'],r;print(r['result'][0]['id'])")
echo "  zone_id=$ZONE_ID"

upsert_record() {
    local type="$1" name="$2" content="$3"
    echo "→ Upsert $type $name → $content (proxied=false)"
    local existing
    existing=$(CF "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?type=$type&name=$name" \
        | python3 -c "import json,sys;r=json.load(sys.stdin);rs=r.get('result') or [];print(rs[0]['id']+'|'+rs[0]['content'] if rs else '')")
    if [ -n "$existing" ]; then
        local existing_id="${existing%%|*}" existing_content="${existing##*|}"
        if [ "$existing_content" = "$content" ]; then
            echo "  ✓ already correct ($existing_id)"
            return 0
        fi
        echo "  → UPDATING existing $existing_id (was: $existing_content)"
        CF -X PUT "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records/$existing_id" \
            -d "{\"type\":\"$type\",\"name\":\"$name\",\"content\":\"$content\",\"ttl\":1,\"proxied\":false}" \
            | python3 -c "import json,sys;r=json.load(sys.stdin);assert r['success'],r;print('  ✓ updated',r['result']['id'])"
    else
        CF -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
            -d "{\"type\":\"$type\",\"name\":\"$name\",\"content\":\"$content\",\"ttl\":1,\"proxied\":false}" \
            | python3 -c "import json,sys;r=json.load(sys.stdin);assert r['success'],r;print('  ✓ created',r['result']['id'])"
    fi
}

upsert_record A "*.fly.app.$ZONE" "$A_V4"
upsert_record AAAA "*.fly.app.$ZONE" "$AAAA_V6"

echo
echo "→ Verify (DNS may take 30-60s to propagate from Cloudflare's edge)"
sleep 5
echo "  A:    $(dig +short @1.1.1.1 test.fly.app.$ZONE A)"
echo "  AAAA: $(dig +short @1.1.1.1 test.fly.app.$ZONE AAAA)"
echo
echo "DONE. To verify the Fly cert+routing chain end-to-end:"
echo "  curl -sS -m 10 https://test.fly.app.$ZONE/web/health    # should return {\"status\": \"pass\"}"
