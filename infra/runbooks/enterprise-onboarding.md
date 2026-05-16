# Enterprise self-host onboarding runbook

Operator procedure for shipping a new paying enterprise customer (self-host tier). Backed by Phase 4.1: the license authority on the control plane + the `saas_license_gate` Odoo addon on the customer's image.

## When to use this runbook

| Scenario | Use this runbook? |
|---|---|
| Customer purchases enterprise self-host | ✅ yes |
| Customer wants to upgrade from shared to self-host | ✅ yes (also run a final shared→archived dump first) |
| Customer wants to renew an expiring license | partial — only the "Mint license" section |
| Customer needs to migrate to a new server | partial — license-id stays; image-digest stays; only HMAC + LICENSE_AUTHORITY_URL re-config needed |
| Customer wants a price quote | no — that's pre-sales, not ops |

---

## One-time platform setup (do this BEFORE the first paying customer)

These are platform-level steps the operator does exactly once. They don't repeat per customer.

### Step 1 — Rotate the Ed25519 signing key

The dev key shipped at `infra/keys/license-signing-pubkey.dev.pem` was generated with the private half printed to a shell scrollback; treat it as compromised.

Generate a fresh keypair **on a trusted workstation** (not in CI, not in chat, not on a shared Mac):

```bash
node -e "
const c = require('crypto');
const { publicKey, privateKey } = c.generateKeyPairSync('ed25519');
require('fs').writeFileSync('/tmp/license-priv.pem',
  privateKey.export({ type: 'pkcs8', format: 'pem' }));
require('fs').writeFileSync('/tmp/license-pub.pem',
  publicKey.export({ type: 'spki', format: 'pem' }));
console.log('wrote /tmp/license-priv.pem (KEEP SECRET) + /tmp/license-pub.pem (commit)');
"
```

Replace the dev pubkey:

```bash
cd ~/Odoo
cp /tmp/license-pub.pem infra/keys/license-signing-pubkey.pem
git rm infra/keys/license-signing-pubkey.dev.pem
git add infra/keys/license-signing-pubkey.pem
git commit -m "chore(license): rotate signing key to production"
git push
```

Set the private half in Vercel (admin, production env only):

```bash
cd ~/Odoo-control-plane/apps/admin
base64 < /tmp/license-priv.pem | tr -d '\n' | pbcopy
vercel env add LICENSE_SIGNING_PRIVATE_KEY_B64 production
# Paste from clipboard when prompted.
```

Trigger a redeploy so the new env reaches the running runtime (`vercel redeploy <latest-url> --target=production` or push any commit).

Securely destroy the local private key:

```bash
shred -uz /tmp/license-priv.pem /tmp/license-pub.pem  # Linux
# or
rm -P /tmp/license-priv.pem /tmp/license-pub.pem      # macOS
```

Smoke-test the live endpoint with `license-cli.sh issue` — see "Mint license" below. A `503 license-signing-key-unset` response means the env var didn't reach the runtime; redeploy.

### Step 2 — Build the enterprise image variant

The shared Odoo image at `ghcr.io/<owner>/odoo-saas-odoo` ships every customer-installable addon EXCEPT `saas_license_gate`. The enterprise variant is the same image rebuilt with the production pubkey COPY'd to `/etc/saas-license-pubkey.pem`:

```bash
# Tag convention: enterprise-<semver> or enterprise-<customer-slug>
ENTERPRISE_TAG=enterprise-v1
docker build \
  --build-arg LICENSE_PUBKEY_FILE=infra/keys/license-signing-pubkey.pem \
  -t ghcr.io/<owner>/odoo-saas-odoo:${ENTERPRISE_TAG} \
  -f Dockerfile .
docker push ghcr.io/<owner>/odoo-saas-odoo:${ENTERPRISE_TAG}
```

Record the resulting image digest — it's what binds the customer's license to a specific image build:

```bash
ENTERPRISE_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' \
    ghcr.io/<owner>/odoo-saas-odoo:${ENTERPRISE_TAG} | sed 's/^.*@sha256://')
echo "image_sha256 = ${ENTERPRISE_DIGEST}"
```

You'll need `${ENTERPRISE_DIGEST}` for both the license-mint step AND the customer's `ODOO_IMAGE_DIGEST` env var.

Recommendation: tag immutably. `enterprise-v1` → `enterprise-v1.1` → `enterprise-v2` (not "latest"). Re-tagging in place breaks the digest-based license binding.

---

## Per-customer onboarding

Repeat for every new paying enterprise customer.

### Step 3 — Pre-flight checks

- ✅ Customer signed the EULA (paper trail required for the contractual half of the threat model — see `models/license_gate.py` in the data plane).
- ✅ Customer's payment cleared.
- ✅ Customer has an `ssh` workstation that can pull from your GHCR (either the image is public, or they have a PAT — see `ghcr-publish.yml` header comments).
- ✅ Customer chose a stable `customer_ref` (typically an email or short slug; used in the `enterprise_licenses.customer_ref` column).

### Step 4 — Mint the license

```bash
cd ~/Odoo
export SAAS_PROVISIONING_SECRET=$(vercel env --cwd ../Odoo-control-plane/apps/admin pull --environment=production --yes /tmp/admin.env >/dev/null && \
                                  grep '^SAAS_PROVISIONING_SECRET=' /tmp/admin.env | cut -d= -f2- | tr -d '"' && \
                                  rm /tmp/admin.env)
export LICENSE_AUTHORITY_URL=https://odoo-saas-admin.vercel.app

# Issue: <customer_ref> <image_sha256> [term_days [grace_days [notes]]]
./infra/scripts/license-cli.sh issue \
    "acme@example.com" \
    "${ENTERPRISE_DIGEST}" \
    365 14 "Q2 2026 enterprise annual"
```

The response includes the `id` field — this UUID is the customer's license_id. **Hand it to the customer out-of-band** (1Password share link, encrypted email, in-person — NEVER plain Slack/Discord/SMS).

### Step 5 — Generate customer-specific HMAC secret

Each enterprise customer gets a **distinct** HMAC secret. The shared SaaS pool uses the pool-wide `SAAS_PROVISIONING_SECRET`; enterprise self-host customers each get their own entry in `SAAS_PROVISIONING_SECRETS_EXTRA` (comma-separated). Revoking one customer's secret means editing the env var to remove their entry, not rotating the pool secret.

```bash
CUSTOMER_HMAC=$(openssl rand -base64 36 | tr -d '/+=' | cut -c1-48)
echo "customer HMAC: ${CUSTOMER_HMAC}"
```

Append to Vercel (admin app, production env):

```bash
cd ~/Odoo-control-plane/apps/admin
# Pull current value
CURRENT=$(vercel env pull /tmp/admin.env --environment=production --yes >/dev/null && \
          grep '^SAAS_PROVISIONING_SECRETS_EXTRA=' /tmp/admin.env | cut -d= -f2- | tr -d '"')
rm /tmp/admin.env

# Append (preserve existing entries, comma-separated)
if [ -n "$CURRENT" ]; then
    NEW_VALUE="${CURRENT},${CUSTOMER_HMAC}"
else
    NEW_VALUE="${CUSTOMER_HMAC}"
fi

# Vercel CLI: remove + re-add (no in-place edit verb)
vercel env rm SAAS_PROVISIONING_SECRETS_EXTRA production --yes 2>/dev/null || true
echo "${NEW_VALUE}" | vercel env add SAAS_PROVISIONING_SECRETS_EXTRA production
```

Trigger redeploy so the new env reaches the runtime:

```bash
vercel redeploy "$(vercel ls --json 2>/dev/null | head -1 | jq -r '.[0].url' || echo '<latest-url>')" --target=production
```

Operator follow-ups documented:
- **Audit log**: every successful `/v1/check` writes a log line with `secret_ref` (`primary` for pool, `extra:<index>` for enterprise). Search Vercel logs by `secret_ref=extra:N` to confirm which customer is hitting the endpoint.
- **Rotation**: to rotate a customer's secret, mint a new HMAC, append to `_EXTRA`, deliver to customer, customer updates their env var + restarts, then remove the old entry from `_EXTRA`.
- **Revocation**: same env-var-edit + redeploy procedure as rotation, just skip the "deliver new" step.

### Step 6 — Deliver the install bundle

The customer needs:

| Item | Value | How |
|---|---|---|
| Image | `ghcr.io/<owner>/odoo-saas-odoo:${ENTERPRISE_TAG}` | Public GHCR or PAT |
| `LICENSE_ID` | UUID from step 4 | Out-of-band |
| `LICENSE_AUTHORITY_URL` | `https://odoo-saas-admin.vercel.app` | Anywhere — not secret |
| `SAAS_PROVISIONING_SECRET` | From step 5 | Out-of-band |
| `ODOO_IMAGE_DIGEST` | `${ENTERPRISE_DIGEST}` (hex digest only, no `sha256:` prefix) | Out-of-band (matches image binding) |
| `ADMIN_PASSWORD` | Strong random | Out-of-band |
| Their own Postgres URL | Customer-managed | Customer-provided |

Recommended docker-compose snippet to share with the customer:

```yaml
services:
  odoo:
    image: ghcr.io/<owner>/odoo-saas-odoo:enterprise-v1
    environment:
      LICENSE_ID: ${LICENSE_ID}
      LICENSE_AUTHORITY_URL: https://odoo-saas-admin.vercel.app
      SAAS_PROVISIONING_SECRET: ${SAAS_PROVISIONING_SECRET}
      ODOO_IMAGE_DIGEST: ${ODOO_IMAGE_DIGEST}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      INIT_MODULES: "saas_license_gate,base"  # CRITICAL — gate must install
      PGHOST: <customer-pg-host>
      PGPORT: "5432"
      PGUSER: <customer-pg-user>
      PGPASSWORD: <customer-pg-pw>
      PLATFORM: customer-self-host
    ports:
      - "8069:8069"
    volumes:
      - odoo-data:/var/lib/odoo
volumes:
  odoo-data:
```

### Step 7 — Verify the first license check lands

Within an hour of customer first-boot, the addon's hourly `ir.cron` should hit the authority. Confirm:

```bash
# Tail Vercel logs for license-check entries
cd ~/Odoo-control-plane/apps/admin
vercel logs --since 1h | grep 'license-check'
```

Expected log shape:

```json
{"level":"info","route":"license-check","msg":"license-check",
 "license_id":"<uuid>","machine_id":"<hex>","status":"active","valid":true}
```

If you don't see entries within ~70 minutes (cron drift), the customer's instance isn't reaching the authority. Walk them through:
1. Is `LICENSE_AUTHORITY_URL` correct?
2. Is the saas_license_gate addon actually installed? (`odoo --list-modules | grep license`)
3. Is the cron enabled? (Settings → Technical → Scheduled Actions → "SaaS: hourly license check")
4. Can the customer's host reach `admin.goliatt.co`? `curl -I https://odoo-saas-admin.vercel.app/api/health` from their server.

### Step 8 — Renewals

The control plane sends three reminder emails per license (Phase 4.1.x) at 90, 30, and 7 days before `expires_at` to the address in the `LICENSE_EXPIRY_NOTIFY_TO` Vercel env var. Set this once during platform setup:

```bash
cd ~/Odoo-control-plane/apps/admin
echo 'operator@example.com' | vercel env add LICENSE_EXPIRY_NOTIFY_TO production
```

Reminders are idempotent — audit_log rows guard against duplicate sends, so re-running the cron is harmless. The 09:00 COT daily cron at `/api/cron/license-expiry-reminders` does the scan.

On renewal day:

```bash
# List the customer's current licenses
./infra/scripts/license-cli.sh list-by-customer "acme@example.com"
# Revoke the old one (optional — they can coexist, but cleaner to retire)
./infra/scripts/license-cli.sh revoke <old-license-id> "Renewed as <new-license-id>"
# Issue the new one with the same image_sha256
./infra/scripts/license-cli.sh issue "acme@example.com" "${ENTERPRISE_DIGEST}" 365 14
```

If the image digest changed (i.e., the customer is also moving to a new enterprise tag), they need to redeploy with the new `ODOO_IMAGE_DIGEST` env var BEFORE the old license expires, otherwise the next cron tick reports `image-mismatch` and the gate flips to invalid.

---

## Revocation procedure

Customer non-payment, breach of EULA, security incident, etc.:

```bash
./infra/scripts/license-cli.sh revoke <license-id> "Non-payment, invoice #1234 90 days past due"
```

Within an hour the customer's hourly cron reports `status: revoked`. The gate's `currently_valid()` flips to `false`; **enforcement decorators on `account.move` / `sale.order` / `stock.picking` are NOT YET WIRED** (Phase 4.1 v0.3 scope explicitly stopped before this), so today's behavior is logging-only. Until decorators ship, revocation is signal + audit trail, not enforcement.

**To force-restore a wrongly-revoked license:**

```bash
# No CLI verb yet; use tRPC directly with operator session OR psql
psql $DATABASE_URL_UNPOOLED -c \
  "UPDATE enterprise_licenses SET revoked_at = NULL, revoked_reason = NULL WHERE id = '<uuid>'"
```

---

## Failure modes

| Failure | Symptom | Fix |
|---|---|---|
| `license-signing-key-unset` 503 | License-cli works for issue/list but `/v1/check` returns 503 | `LICENSE_SIGNING_PRIVATE_KEY_B64` missing from Vercel; set it + redeploy |
| `bad-signature` 401 on /v1/check | Customer reports "license invalid" log line "SIGNATURE VERIFICATION FAILED" | Pubkey in their image doesn't match the operator's private key. Probably they're on the OLD `enterprise-v1` image after a key rotation. Rebuild with rotated pubkey, customer pulls new tag. |
| `image-mismatch` status | Customer ran fine yesterday, today reports `valid=false image-mismatch` | They upgraded their image and the new digest doesn't match the license. Re-mint license with new digest or revert customer's image. |
| `network-failed` for >14 days | Customer's gate locks to `stale` even after they come back online | Customer firewalled the authority. Once they reach it, the next successful tick clears stale. If they were down >14d AND past grace_until, the stale period stacks on top — extend grace_until manually via tRPC.
| `pre_init_hook` fails on install | Customer can't bootstrap a fresh DB | Their env vars are wrong. Walk them through step 6 again. |

---

## Out-of-scope (not in this runbook)

- Wire transfer + invoice issuance — Finance team
- DIAN e-invoice for the customer's purchase — Jorels addon in operator Odoo DB
- KYC / EULA collection — Sales/Legal
- Customer's own DB / backup strategy — explicitly customer-managed in self-host tier
- Support tickets, SLA — separate runbook
