# Observability — native logs only (current state)

HARDENING.md item 2 calls for log aggregation across Vercel + Railway + Fly into a single vendor. Operator decision (2026-05-14): **skip the external vendor for this phase**. Rely on each platform's native log viewer + the structured-JSON output we now emit in critical paths.

## What you have today

| Source | Where to look | Retention | Search |
|---|---|---|---|
| Vercel admin functions | `vercel logs odoo-saas-admin.vercel.app --since 1h` or the Vercel dashboard | **1h on Hobby**, 30d on Pro/Enterprise | full-text + structured field filters in dashboard |
| Vercel portal functions | `vercel logs odoo-saas-portal.vercel.app --since 1h` | same | same |
| Railway Odoo + Postgres | Railway dashboard → service → Logs tab; or `railway logs --service <name>` | ~7 days on Hobby | per-service stream, no cross-service correlation |
| Fly Odoo + Postgres | `flyctl logs --app <app>` | **streaming only, no retention** | grep on the live stream |
| GitHub Actions (pgBackRest backups, restore drills, CI) | `gh run view <id> --log` or repo Actions tab | 90 days default | per-run search |

## What we lose without a drain

- No cross-platform correlation (a tenant signup spans portal → admin → Odoo pool; tracing that today means three separate viewers).
- No retention beyond the platform defaults; Fly's zero retention is the worst gap.
- No automated alerting on the conditions HARDENING.md item 2 calls out:
  - Vercel function errors > N/min
  - Odoo CRITICAL lines
  - pgBackRest backup-runner non-zero exits
  - Cron failures
  - Resend rejection in `emailWelcome`

Operationally that means: failures get noticed by tenants before us, or by the next operator visit to the dashboards. Acceptable for a private pilot; not acceptable once paying tenants are on.

## Structured-JSON log lines already in place

These flow through whichever platform runs the code; if you ever flip the vendor decision, every drain ingests them as-is — no rewrite needed.

- `apps/admin/app/api/internal/cluster-backups/route.ts` — `{level, route, msg, op, ...}` per sync/drill_pass/sweep_untrusted call
- `apps/admin/app/api/cron/outbox-tick/route.ts` — `{level, route, msg, pulled, handled, noopped, failed}` per tick + auth-failure warns
- `packages/workflows/src/provision-tenant.ts` — `[loadTenant] row=`, `[emailWelcome] inputs=` instrumentation for the provisioning pipeline

When new code lands, follow the same shape: `console.log(JSON.stringify({level, route, msg, ...extra}))`.

## Future activation (when you're ready)

If/when you upgrade to a vendor:

1. Sign up at https://axiom.co (recommended — Vercel-native), create a dataset `odoo-saas`, generate an Ingest-scope API token.
2. Paste the token back to me (or set it manually):
   - Vercel: Project Settings → Logs → "Connect a Log Drain" → Axiom → paste token. Repeat for admin + portal.
   - Railway: Project Settings → Log Drains → New Drain → Generic Webhook → URL `https://api.axiom.co/v1/datasets/odoo-saas/ingest`, header `Authorization=Bearer <token>`.
   - Fly: deploy `superfly/fly-log-shipper` as a new Fly app on the same org, secrets `AXIOM_TOKEN`, `AXIOM_DATASET`, `ORG`, `ACCESS_TOKEN` (org-read scope from `flyctl tokens create org-read`).
3. Configure the 8 monitors from `alerts.json` in the Axiom UI.

## Operational practice while we have no aggregation

- Check Vercel + Railway + Fly dashboards on a weekly cadence.
- The pgBackRest workflows (`.github/workflows/pgbackrest-backup.yml` and `restore-drill.yml`) email-on-failure via the GitHub repo's notification settings — make sure repo notifications are on for the operator's GitHub account.
- The cron-tick workflow on Vercel emits a structured summary every minute; in the absence of alerting, check `vercel logs` for `failed > 0` lines after any webhook-handler change.
- `cluster_backups` table in Neon is the canonical record of which backups have been drill-tested — query it directly when in doubt:
  ```sql
  SELECT platform, state, count(*) FROM cluster_backups GROUP BY 1,2;
  ```

## Alert definitions (parked, not active)

`alerts.json` in this dir holds the eight alert queries we'd want if we had a vendor. They're written in Axiom's APL but are simple enough to translate to any vendor's query language. Keep them up to date alongside the code changes they observe so they're ready to wire when you flip the decision.
