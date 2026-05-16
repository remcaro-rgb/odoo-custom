# Phase 4.1 Shipped — Enterprise Self-Host Licensing

**Date:** 2026-05-16
**Scope:** Continue autonomous work — Phase 4.1 (enterprise license authority + saas_license_gate addon)
**Status:** Code-complete, deployed. Two manual operator follow-ups remaining before first enterprise customer.

This document is the landing page for the licensing-system work; the parallel `2026-05-16-afk-session-summary.md` covers a different (agent-runtime) scope from the same morning.

---

## What shipped (4 commits per repo, ~1,000 lines)

### Control plane (`Odoo-control-plane` repo)

| Commit | Scope |
|--------|-------|
| `f557043` | License authority — schema (migration 0007 applied to live Neon), `enterpriseLicensesRouter` tRPC (operator-only `issue/revoke/restore/list/get/check`), HMAC-gated `POST /api/internal/license/check` HTTP endpoint with Ed25519-signed response payload. |
| `8482343` | Operator HMAC endpoints — `/api/internal/license/{issue,revoke,list}` mirror the tRPC surface without Clerk session, so the operator CLI can drive them from a terminal. |

### Data plane (`odoo-custom` repo)

| Commit | Scope |
|--------|-------|
| `c88ea54` | Cosign keyless signing in `ghcr-publish.yml` — every published image (odoo, postgres, backup-runner) is signed by digest via GitHub OIDC → Sigstore Fulcio → Rekor. (Already shipped earlier in the day; included here for completeness as it's Phase 4.1 v0.1.) |
| `91cd9d8` | Dev license-signing pubkey scaffolding at `infra/keys/license-signing-pubkey.dev.pem` + full production rotation runbook in `infra/keys/README.md`. |
| `bfd03e1` | New `custom-addons/saas_license_gate/` addon — `pre_init_hook` refuses install without env config, hourly `ir.cron` calls authority + verifies Ed25519 signature, `current_status()/currently_valid()/currently_in_grace()/allowed_modules()` are public verdict accessors. Dockerfile takes `--build-arg LICENSE_PUBKEY_FILE=...`. |
| `5db62c1` | `infra/scripts/license-cli.sh` — pure-bash operator CLI for issue/revoke/list-by-customer/list-by-image. Zero install footprint (curl + openssl + date + optional jq). |

Both repos pushed to `main` on GitHub. Vercel auto-deployed control plane (production alias `https://odoo-saas-admin.vercel.app`). Data plane changes activate on the next `ghcr-publish.yml` run.

---

## Architecture at a glance

```
                                          ┌─────────────────────────────┐
   operator workstation                   │  Vercel admin app           │
       │                                  │  /api/internal/license/...  │
       │  HMAC over body                  │  (HMAC-gated, Ed25519       │
       │                                  │   signs response payload)   │
       ▼                                  └────────────┬────────────────┘
   license-cli.sh ────────────────────────────────────►│
                                                       │
                                            POST /v1/check
                                                       │
                                                       ▼
       ┌────────────────────────────────────────────────────────────────┐
       │  Customer self-host Odoo installation                          │
       │                                                                │
       │  hourly ir.cron in saas_license_gate                           │
       │      → POST authority with {license_id, image_sha256,          │
       │                              machine_id, timestamp}            │
       │      → Ed25519 verify(response.payload, response.signature,    │
       │                       pubkey from /etc/saas-license-pubkey.pem)│
       │      → persist status to ir.config_parameter                   │
       │                                                                │
       │  enforcement decorators (future) read current_status() and     │
       │      block account.move/sale.order/stock.picking writes when   │
       │      status ∉ {active, grace}.                                 │
       └────────────────────────────────────────────────────────────────┘
```

Why two crypto layers (HMAC + Ed25519): the HMAC keeps random internet traffic off the endpoint, but a leaked HMAC secret would let an attacker forge `valid=true` responses. Ed25519 over the response payload (signed with a key the operator holds offline) is the actual trust anchor.

---

## What I deliberately did NOT do

1. **Generate a production Ed25519 keypair.** The dev key at `infra/keys/license-signing-pubkey.dev.pem` had its private half printed to a shell scrollback during scaffolding, so it's unsafe for paying customers. The rotation procedure in `infra/keys/README.md` is the operator's task on a trusted workstation; doing it autonomously would have meant either committing a secret to chat (no) or assuming an offline workstation that I don't have access to (no).

2. **Configure `LICENSE_SIGNING_PRIVATE_KEY_B64` in Vercel.** Same reason. Without this env var, `POST /api/internal/license/check` returns `503 license-signing-key-unset` — which I verified during the e2e check; the deploy is otherwise healthy.

3. **Apply enforcement decorators to `account.move` / `sale.order` / `stock.picking`.** `currently_valid()` is wired and ready; no model in the addon actually calls it yet. Add when the first enterprise customer reaches production — premature decorators are easy to land in a broken state and hard to debug under pressure.

4. **Build the enterprise-variant image.** The Dockerfile takes `--build-arg LICENSE_PUBKEY_FILE=...` but the GHCR workflow doesn't yet publish a separate enterprise tag. When v0.5 lands a customer onboarding workflow, that's the right moment to extend `ghcr-publish.yml` with a second matrix entry (`enterprise-v1` tag, rotated pubkey).

---

## Operator follow-ups (in order)

1. **Generate production keypair** per `infra/keys/README.md`. Replace the dev `.pem`, commit + push, **shred the private file** after pushing the base64 to Vercel:

   ```
   base64 < /tmp/license-priv.pem | tr -d '\n' | pbcopy
   vercel env add LICENSE_SIGNING_PRIVATE_KEY_B64 production
   # paste from clipboard
   shred -uz /tmp/license-priv.pem  # or rm -P on macOS
   ```

2. **Smoke-test the live `/v1/check` endpoint** after the env var lands. The license-cli.sh script (with `LICENSE_AUTHORITY_URL=https://odoo-saas-admin.vercel.app` + `SAAS_PROVISIONING_SECRET` set) can run the full lifecycle: issue → list → revoke → list, plus a direct `curl` of `/api/internal/license/check` to verify a `valid=true` payload signs correctly.

3. **First enterprise customer onboarding** (when one arrives):
   - Build enterprise image with `--build-arg LICENSE_PUBKEY_FILE=infra/keys/license-signing-pubkey.pem`.
   - Push to GHCR with an enterprise-only tag.
   - Mint license via `license-cli.sh issue`.
   - Provide customer with `{LICENSE_ID, LICENSE_AUTHORITY_URL, SAAS_PROVISIONING_SECRET, ODOO_IMAGE_DIGEST}` env vars + image pull credentials.
   - Watch the first hour of license-check telemetry to confirm hourly cron lands.

---

## Files inventory

### Control plane

```
packages/db/src/schema.ts                                   (enterprise_licenses table)
packages/db/drizzle/0007_wide_corsair.sql                   (migration; applied live)
packages/api/src/routers/enterprise-licenses.ts             (tRPC)
packages/api/src/routers/_app.ts                            (mount)
packages/api/package.json                                   (export ./routers/enterprise-licenses)
apps/admin/app/api/internal/license/_lib.ts                 (shared HMAC verifier)
apps/admin/app/api/internal/license/check/route.ts          (customer endpoint)
apps/admin/app/api/internal/license/issue/route.ts          (operator)
apps/admin/app/api/internal/license/revoke/route.ts         (operator)
apps/admin/app/api/internal/license/list/route.ts           (operator)
```

### Data plane

```
infra/keys/license-signing-pubkey.dev.pem                   (DEV ONLY — rotate before prod)
infra/keys/README.md                                        (rotation runbook)
custom-addons/saas_license_gate/__manifest__.py
custom-addons/saas_license_gate/__init__.py
custom-addons/saas_license_gate/hooks.py
custom-addons/saas_license_gate/models/__init__.py
custom-addons/saas_license_gate/models/license_gate.py
custom-addons/saas_license_gate/data/ir_cron_data.xml
custom-addons/saas_license_gate/security/ir.model.access.csv
Dockerfile                                                  (ARG LICENSE_PUBKEY_FILE + COPY)
infra/scripts/license-cli.sh                                (operator bash CLI)
```

### Memory updated

- `~/.claude/projects/-Volumes-SATECHI2TB-userfolder-Odoo/memory/project_saas_plan.md` — Phase 4.1 status block appended.

---

## Numbers

- **Control-plane LOC added:** ~600 (router 195 + check route 165 + operator routes 200 + lib 60)
- **Data-plane LOC added:** ~470 (addon 350 + CLI 170 — runbook excluded)
- **Migrations applied to live Neon:** 1 (`0007_wide_corsair.sql`)
- **New tables:** 1 (`enterprise_licenses`)
- **New HTTP endpoints in admin:** 4 (`license/check`, `license/issue`, `license/revoke`, `license/list`)
- **New tRPC procedures:** 6 (`enterpriseLicenses.{issue, revoke, restore, list, get, check}`)
- **New Odoo addon:** 1 (`saas_license_gate`)
- **Commits pushed:** 6 total (2 control-plane, 4 data-plane)

Welcome back, Manu.
