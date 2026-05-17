# Operator License-Management UI — Design Spec

**Date:** 2026-05-17
**Author:** Manuel Caro (with Claude)
**Status:** Draft
**Spec type:** design spec (follows §2.4 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Scope of work:** First operator-facing UI slice in `apps/admin` of the control plane. Replaces day-to-day use of `infra/scripts/license-cli.sh` with a web UI that has full CLI parity (mint, revoke, restore, list) plus a generic audit-log viewer and a `/v1/check` signing-key probe.

---

## 1. Goal

Build the first real UI inside `apps/admin` so the Goliatt operator can manage enterprise self-host licenses, audit historical actions across all namespaces (license / tenant / backup / email), and verify the live license-signing key from a browser. Today these operations require shell access plus `infra/scripts/license-cli.sh`, which is acceptable for one operator but becomes friction-prone as the team grows past one. The UI also lays the foundation (auth layout, component library, server-action pattern, test infra) that future operator-app slices — tenant CRUD, plan CRUD, manual provision, backup-catalog viewer — will build on without re-deciding architecture each time.

## 2. Non-goals

- Customer-portal UI in `apps/portal`. Separate spec after enterprise customer #1.
- Tenant CRUD, plan CRUD, manual provision dashboard, backup-catalog viewer, dual-approval restore trigger. Each gets its own spec.
- Per-customer HMAC management UI. The `SAAS_PROVISIONING_SECRETS_EXTRA` env-var edit stays a manual operator step covered by the runbook.
- Renew-as-one-action (atomic revoke-old + issue-new in a single transaction). v1 surfaces both buttons; operator clicks both. Can be added as v2.
- Image-digest autocomplete from recent GHCR `enterprise-v*` tags. v1 is plain-text input; v2 nice-to-have.
- Optimistic UI updates on mutations. v1 always waits for the server round-trip; correctness over snappiness.
- Visual-regression testing (Percy / Chromatic). v1 has functional tests only.
- Customer/operator chat or notification surface. The existing `license-expiry-reminders` cron + Resend email path is the only proactive comm channel.

## 3. Tenancy impact

**No per-tenant data is touched.** This UI operates exclusively against the control-plane Neon database tables `enterprise_licenses` and `audit_log`, both of which live OUTSIDE any tenant boundary. No tenant DB is queried, modified, or even named. The `saas_tenant_gate` seat-cap, telemetry, and feature-flag mechanisms are unaffected.

**Cross-tenant leak risk:** zero. The control plane has no row-level tenancy column on these tables; every row is operator-internal. The UI's filter inputs (`customer_ref`, `image_sha256`) operate on enterprise-self-host customers, who by definition have no shared-pool tenancy at all.

**Audit-log viewer scope:** the page shows ALL rows in `audit_log`, including rows whose `target_type = 'tenant'` reference shared-pool tenant operations. This is acceptable because (a) the operator role already has full read access via the control-plane DB, and (b) the audit_log table never carries tenant-customer PII beyond names/emails already in the operator's view from the existing `tenants` table.

## 4. Data model changes

**None.** This is a pure UI slice over existing tables:

- `enterprise_licenses` (shipped Phase 4.1 v0.2, migration `0007`). Columns: id, customer_ref, image_sha256, expires_at, grace_until, allowed_modules (jsonb), revoked_at, revoked_reason, notes, created_at.
- `audit_log` (existing). Columns: id, ts (timestamp), actor_user_id, action, target_type, target_id, payload (jsonb). The Drizzle model is in `packages/db/src/schema.ts`; the UI does not add columns.

No new tables, columns, indexes, or constraints. No migration.

## 5. API surface

**Reused unchanged from `packages/api/src/routers/enterprise-licenses.ts`:**

- `enterpriseLicenses.get({ id })` — query, operator-only.
- `enterpriseLicenses.issue({ customerRef, imageSha256, termDays?, graceDays?, allowedModules?, notes? })` — mutation, operator-only.
- `enterpriseLicenses.revoke({ id, reason })` — mutation, operator-only.
- `enterpriseLicenses.restore({ id })` — mutation, operator-only.

**Extended (the existing procedure stays backwards-compatible):**

- `enterpriseLicenses.list({ customerRef?, imageSha256?, status?, from?, to?, cursor?, limit? })`. The current procedure requires `customerRef OR imageSha256`. The dashboard's unfiltered first render needs both to be optional. Relax the `refine()` constraint so an empty filter returns the most-recent N rows. Add four optional fields:
  - `status: 'active' | 'grace' | 'expired' | 'revoked' | 'all'` — derived state, NOT a column. Compiled to SQL `WHERE` clauses using `now()` and the existing `revoked_at` / `expires_at` / `grace_until` columns:
    - `active` → `revoked_at IS NULL AND expires_at > now()`
    - `grace` → `revoked_at IS NULL AND expires_at <= now() AND grace_until > now()`
    - `expired` → `revoked_at IS NULL AND grace_until <= now()`
    - `revoked` → `revoked_at IS NOT NULL`
    - `all` → no extra clause
  - `from` / `to` (ISO timestamps) — `createdAt` range.
  - `cursor` (uuid + createdAt tuple, opaque base64) — for cursor pagination. `limit` defaults to 50, max 200.

  Callers that pass the old shape (with one of customerRef/imageSha256, no status/cursor) keep working. The CLI doesn't break.

**New tRPC router — `packages/api/src/routers/audit.ts`:**

- `audit.list({ actionPrefix?, targetType?, targetId?, actor?, from?, to?, cursor?, limit? })` — read-only, operator-only. Generic query over the existing `audit_log` table. `actionPrefix` filter matches via `LIKE 'license.%'` etc. `cursor` / `limit` same shape as the licenses list.

**Reused unchanged:** `POST /api/internal/license/check` — the signing-key probe page calls this internally with a sentinel HMAC envelope (same logic as `license-cli.sh verify-signing-key`).

**Reused (unchanged):** `POST /api/internal/license/check` — the signing-key probe page calls this internally with a sentinel HMAC envelope (same logic as `license-cli.sh verify-signing-key`).

**New server actions (in `apps/admin/lib/actions/licenses.ts`):** thin wrappers around the tRPC procedures, plus `probeSigningKeyAction()`. Each returns `{ ok: true, data } | { ok: false, error: { code, message, fieldErrors? } }` per the contract in § 5 of the brainstorming output.

## 6. Security model

**Authentication:** Clerk via the existing `apps/admin/proxy.ts` middleware. Sessions checked at request time. No change to Clerk configuration; reuses the project's existing organization and user setup.

**Authorization (layered, three checks):**

1. **Middleware (`proxy.ts`):** any unauthenticated request → redirect to Clerk sign-in. No change.
2. **Layout `AuthGate` (server component, new):** resolves `clerkClient.users.getUser(userId)`, asserts `publicMetadata.role === 'operator'`. Otherwise `redirect('/not-authorized')`. Wrapped in React `cache()` so the lookup runs once per request. Matches the existing pattern from `app/api/trpc/[trpc]/route.ts` (`eb460bd`: OPERATOR_USER_IDS env-var fallback was removed; metadata is sole truth).
3. **tRPC procedures:** every `enterpriseLicensesRouter` procedure is `operatorProcedure` and checks `ctx.session.isOperator`. Already in place; no change.
4. **Server actions:** repeat layer 2's check inline before invoking the tRPC caller. Defense-in-depth; catches a non-operator who knows a server-action URL.

**Sensitive data exposure:** the audit-log payload field can contain JSON that includes the per-request HMAC signature from the incoming `/v1/check` envelope and the outgoing Ed25519 signature on the response payload. Neither is a long-lived secret — HMAC signatures are single-use with a ±300 s timestamp window, and Ed25519 signatures are verifiable proofs that anyone holding the pubkey can validate. The JSON payload modal renders these as `<pre>` text without redaction. Acceptable: only operators can see this page, and the payload is already what their browser would see via the Neon dashboard. No raw secrets (`SAAS_PROVISIONING_SECRET`, `LICENSE_SIGNING_PRIVATE_KEY_B64`) are ever written to `audit_log.payload`.

**Tenancy-isolation argument:** this UI operates on control-plane-only tables (`enterprise_licenses`, `audit_log`). It never queries a tenant database, never references a `tenant_id` for read or write, and never crosses the per-tenant boundary. There is no row-level tenancy gating to evaluate because the data is intrinsically non-per-tenant. Even the audit-log viewer, which surfaces some `target_type = 'tenant'` rows from other namespaces, only displays operator-visible metadata (tenant slug, action) that's already in the operator's view via the existing tenants router.

## 7. Test plan

**Unit (vitest in `packages/api`, `apps/admin`):**

- `evaluateLicense()` — pure function. Cover: active, grace (between expires_at and grace_until), expired (past grace_until), revoked, image-mismatch, boundary transitions. ~10 cases.
- Server actions (`apps/admin/lib/actions/licenses.ts`) — for each of `mintLicenseAction`, `revokeLicenseAction`, `restoreLicenseAction`, `probeSigningKeyAction`: success path, zod-validation failure (`VALIDATION` code), auth missing (`UNAUTHORIZED`), conflict (e.g., revoke already-revoked), internal error (mocked Drizzle throw). ~20 cases. Mock the tRPC caller via vi.mock; no DB hit.
- `LicenseStatusBadge` rendering — given a row + a `now`, asserts the right variant + label. ~6 cases. React Testing Library.

**Integration (vitest with ephemeral Neon branch):**

- One pass per mutation server action that runs against `neon branches create --parent=main --name=ci-$run_id` and tears down. Asserts the DB state AND the audit_log row. ~4 tests. Setup helper in `packages/api/test/integration-setup.ts`. Runs in ~10 s with a warm Neon branch.

**E2E (Playwright on Vercel preview URLs):**

1. `auth.operator-can-access.spec.ts` — Clerk test user with operator role visits `/licenses`, sees the table render.
2. `auth.non-operator-bounced.spec.ts` — non-operator Clerk user → redirected to `/not-authorized`.
3. `mint.spec.ts` — fill mint form, submit, redirect to detail, navigate back, row appears in dashboard.
4. `revoke-restore.spec.ts` — revoke via dialog with reason, status flips, detail audit log shows new entry; restore, status flips back; second audit entry.
5. `signing-key.spec.ts` — `/signing-key` probe returns PASS.

Run on per-PR preview deployment with a test Clerk org. Skipped on main pushes (the preview env is the only one with a test Clerk org wired). ~3 min wall-clock total.

**Adversarial:**

- Non-operator Clerk user attempting direct POST to `/_actions/revoke-license-action` (or whatever the Next.js Server Action endpoint resolves to) — assert 403/redirect, no DB mutation.
- Filter param injection: `?status=' OR 1=1 --` reaches the Drizzle query — assert it's escaped (Drizzle parameterizes); status falls back to defaults via zod.
- Long `notes` field (10 KB) — assert it's accepted (text column has no length limit) and renders without breaking the detail page.

**CI wiring:**

A new `test-control-plane` job in `.github/workflows/ci.yml` (or a control-plane-specific workflow if the project moves to per-app workflows by then). Matrix: `pnpm --filter @odoo-saas/api test`, `pnpm --filter @odoo-saas/admin test`, `pnpm --filter @odoo-saas/admin e2e`. Required check on PRs touching `apps/admin/**`, `packages/api/src/routers/enterprise-licenses.ts`, `packages/api/src/routers/audit.ts`, `packages/db/src/schema.ts`.

## 8. Rollout plan

**Feature flag:** none. The UI replaces a CLI flow that's already in production; there's no parallel state to gate. Operator can keep using `license-cli.sh` while the UI is being built (the CLI keeps working).

**Deploy sequence:**

1. Land `packages/api/src/routers/audit.ts` (new file, additive) AND extend `enterpriseLicenses.list` per § 5 (relax refine, add status/from/to/cursor). Both are additive and backward-compatible with `license-cli.sh`. Deploy admin app — adds tRPC procedures, no UI change yet. Unit tests for the new status SQL gates land in this PR.
2. Add Tailwind v4 + shadcn/ui to `apps/admin`. Install primitives. Deploy — admin page.tsx unchanged.
3. Add layout shell + AuthGate + sidebar. Deploy — operator sees the shell but only `/` and `/not-authorized` work.
4. Land `/licenses` (list) + `/licenses/[id]` (detail) read-only. Deploy.
5. Land mint/revoke/restore actions + their UI. Deploy.
6. Land `/audit` viewer. Deploy.
7. Land `/signing-key`. Deploy.

Each step is a separate PR. Each PR is independently revertible.

**Migration cost:** zero. No DB rows touched.

**Rollback path:** revert the offending PR. The CLI flow continues to work because the tRPC procedures are unchanged.

**Wave:** canary (deploy to production directly — the admin app is operator-only, no public traffic). No staged rollout needed.

## 9. Observability

**Logs:**

- Every server action logs structured JSON to Vercel logs: `{action: "revokeLicense", actor: <userId>, licenseId, ok: true/false, error?: <code>, duration_ms}`.
- The existing `audit_log` row insertion in the tRPC procedure (already there from Phase 4.1) remains the canonical record. Server-action logs are redundant — for fast incident response when Neon is itself slow.
- Field redaction: no secrets are logged (HMAC signatures, image digests are OK; license_id, customer_ref are OK; nothing else is sensitive).

**Metrics:**

- None new. The audit_log table IS the metric source; queryable on demand. If page-level perf becomes an issue, add a Vercel Analytics counter on `/licenses` render duration.

**Alerts:**

- None new. The existing `license-expiry-reminders` cron (`/api/cron/license-expiry-reminders`, 09:00 COT daily) already alerts on customer-license expiry. UI doesn't introduce new alert sources.

## 10. Open questions

1. **Pagination strategy: cursor or offset?** The tRPC `list` procedure currently returns up to 100 rows without a cursor. With <1000 total licenses anticipated for years, offset pagination is simpler and equally fast. Recommendation: page size 50, offset-based, `?page=N` URL param. **Decide at implementation.**

2. **Should the audit-log viewer link to specific entity detail pages for non-license `target_type` rows?** e.g., `target_type='tenant'` → link to `/tenants/[id]` page. Those pages don't exist yet (deferred to future spec). For v1: rows whose `target_type != 'license'` show the `target_id` as plain text, no link. Reconsider when tenant CRUD lands.

3. **What's the Clerk test-user / test-org setup for E2E?** The control plane has a real Clerk integration; we need separate test users in a test org for Playwright. Two paths: (a) Clerk's testing-token utility, (b) a dedicated Clerk dev project pointed at the preview env. **Decide before Playwright lands; not blocking earlier steps.**

4. **Tailwind v4 + shadcn/ui in a Next 16 monorepo with the existing pnpm workspace — any known integration gotchas?** Spot-check: `npx shadcn add` writes to `apps/admin/components/ui/` and registers a `components.json`; should work without monorepo-specific surgery, but worth a 30-min probe before committing to the stack across future operator-app slices.

5. **Audit-log payload field can contain large JSON (e.g. full signed license-check responses, ~3 KB). Does the modal need lazy-load or pagination of the payload itself?** v1 renders the full JSON — assume <10 KB per row is fine. Reconsider if a single payload ever exceeds ~50 KB.
