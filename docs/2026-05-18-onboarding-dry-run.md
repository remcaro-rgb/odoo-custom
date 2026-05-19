# Enterprise customer onboarding dry-run — 2026-05-18

Walking the production onboarding runbook (`infra/runbooks/enterprise-onboarding.md`) end-to-end without an actual customer, to surface gaps before customer #1 lands.

**Image under test:** `ghcr.io/remcaro-rgb/odoo-saas-odoo-enterprise:enterprise-v1@sha256:7e84600695f45b7a06634375085271e270e8d44bbb8ac649bf929c2a65c92114`
**Authority URL:** https://odoo-saas-admin.vercel.app
**Operator UI:** live (PR #1 squash-commit 08f371d)

---

## Step 3 — Pre-flight checks: ✅ pass

Runbook says to verify the enterprise image is publishable and signed. Confirmed during Phase 4.1 follow-up #2 (2026-05-17): the `enterprise-v1` image is in GHCR, cosign-signed via GitHub OIDC, digest `7e846006…` matches the build's Step Summary.

Also implicitly covered by today's prod smoke walk: `/signing-key` probe returned PASS (HTTP 404 with valid signature), confirming the license authority is up and signing key is loaded.

---

## Step 4 — Mint the license: ✅ verified two ways

Today's smoke walk exercised this twice:
- `customer_ref=smoketest@goliatt.co` with `aaaa…` (placeholder digest)
- `customer_ref=remcaro@icloud.com` with `7e846006…` (real enterprise-v1 digest)

Both minted cleanly through the new operator UI's `/licenses/new` form. Audit rows landed correctly. Both revoked after the smoke walk (commit-equivalent: direct DB UPDATE today, 2026-05-18; in production the operator would click the Revoke button).

**Runbook update suggested:** Step 4 currently documents only the `license-cli.sh issue` flow. **Add the operator UI path** ("Open /licenses/new in admin, fill the form, submit") as the recommended approach. CLI stays as fallback.

---

## Step 5 — Generate customer-specific HMAC secret: ⚠️ documented but not exercised

The runbook procedure is:
1. `openssl rand -base64 32` → per-customer secret
2. Concatenate into `SAAS_PROVISIONING_SECRETS_EXTRA` (comma-separated) in Vercel admin Production env
3. Redeploy admin
4. Hand the secret to the customer out-of-band

**Not exercised** because doing so writes a real entry to production env vars. The `verifyHmacEnvelope()` helper in `apps/admin/lib/hmac-secrets.ts` (Phase 4.1.x `c61e7b2`) is already wired to accept these; no code path needs verification.

**Gaps surfaced:**
1. The runbook says to use `vercel env` for the env var update — but the Sensitive flag would block reading the existing list. Operator must keep the running list of customer secrets in a password manager (or use the REST API approach we documented in [[reference-vercel-env-add-preview-action-required-loop]] for the read).
2. No tool exists yet for *removing* a customer secret. To rotate (e.g., after customer terminates), the operator must:
   - Pull `SAAS_PROVISIONING_SECRETS_EXTRA` via env-pull
   - Remove the target entry from the comma list
   - `vercel env rm` then re-add the cleaned list
   - Redeploy

**Recommend:** add `infra/scripts/customer-hmac.sh` with `add` and `remove` subcommands as a v2 follow-up. Not blocking; manual procedure works.

---

## Step 6 — Deliver the install bundle: ✅ doc exists

`docs/enterprise-customer-install.md` (committed in Phase 4.1 follow-up batch e40100c) covers everything the customer needs: docker-compose template, `.env` template, first-boot expectations, troubleshooting matrix, backup recommendations, support contacts.

Hand the customer:

| Value | Source | Sensitivity |
|---|---|---|
| `LICENSE_ID` | UUID from the row in `enterprise_licenses` after minting | Customer-identifying, treat as confidential |
| `SAAS_PROVISIONING_SECRET` | Per-customer secret from Step 5 | Secret |
| `ODOO_IMAGE_DIGEST` | `7e84600695f45b7a06634375085271e270e8d44bbb8ac649bf929c2a65c92114` (current `enterprise-v1`) | Not secret |
| `LICENSE_AUTHORITY_URL` | `https://odoo-saas-admin.vercel.app` | Not secret |
| `ADMIN_PASSWORD` | `openssl rand -base64 24` (operator generates) | Secret — instruct customer to rotate after first login |
| Image pull credentials | GHCR is currently private — operator must either make `odoo-saas-odoo-enterprise` package public on GHCR, OR mint a customer-scoped GHCR PAT and include it | Secret if PAT |

**Gap surfaced:** GHCR `odoo-saas-odoo-enterprise` package visibility is currently PRIVATE (set by default on first push). For the first customer, either:
- Make the package public on GHCR (settings → "Change visibility" → Public) — anyone can pull, but only operator can push
- Provide a customer-scoped GHCR PAT and document it in their install bundle

**Recommend public** for the enterprise package. There's nothing secret in the image (the pubkey is intentionally embedded; the source is on github.com/GoliattCo/odoo-custom anyway).

---

## Step 7 — Verify the first license check lands: ⚠️ requires real install

Cannot dry-run without a customer Odoo instance pulling the image and booting with the env vars. The addon's hourly cron POSTs to `/api/internal/license/check` and the response gets logged to `audit_log` (`license.check` action). Operator monitors via the new `/audit` UI page with filter `namespace=license`.

**The `/audit` page renders correctly** (verified in today's smoke walk). The license-check rows would appear there with the customer's `license_id` as `target_id`.

**Implicit gap:** there's currently no automated alert when a customer's license-check stops landing (i.e., they went offline). The hourly cadence + 14-day stale grace gives a long detection window. Could add a `license-staleness-reminder` cron parallel to the `license-expiry-reminders` we already ship — not in scope for v1.

---

## Step 8 — Renewals: ✅ doc-only path

Operator workflow:
1. Detail page for the about-to-expire license
2. Click Revoke (reason="renewal: superseded by new license-id")
3. `/licenses/new` → mint a fresh license with the same customer_ref + same image_sha256, new term
4. Send the new `LICENSE_ID` to the customer; they update their `LICENSE_ID` env var

**Gap surfaced:** this is two-click + an out-of-band notification. Spec §10 q12 already tracks the "renew-as-one-action atomic mutation" as a v2 deferred feature.

The `license-expiry-reminders` cron (Phase 4.1.x `3f5dd44`) already fires 90/30/7d warnings via Resend to the `LICENSE_EXPIRY_NOTIFY_TO` operator inbox; the operator gets paged in time to do the manual two-step.

---

## Summary

**Steps fully ready:** 3 (pre-flight), 4 (mint), 6 (install bundle docs), 8 (renewals).
**Steps with documented gaps but workable:** 5 (per-customer HMAC tooling), 7 (no staleness alert).
**Step missing operator action:** none — every step is doable today by a properly-trained operator.

**Before customer #1 hits:**
1. Make `ghcr.io/remcaro-rgb/odoo-saas-odoo-enterprise` package public on GHCR (or pre-mint a customer PAT). **Required.**
2. ~~Confirm `LICENSE_EXPIRY_NOTIFY_TO` env var is set in Vercel admin Production~~ — **DONE 2026-05-18**: dry-run discovered it was unset (the expiry-reminder cron would have silently no-op'd); now set to `remcaro@gmail.com` in both Production and Preview via Vercel REST API.
3. Confirm operator has a place to securely store the per-customer HMAC secrets and license_ids. A password-manager vault works. **Recommended.**

**No code changes blocking the first paying customer.** When they're ready, the operator can run through Steps 4–6 end-to-end in ~15 minutes.
