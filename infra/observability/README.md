# Observability — log drains + alerts

This implements HARDENING.md item 2.

The control plane (Vercel admin + portal), data plane (Railway + Fly Odoo + Postgres), and the GitHub Actions backup/drill workflows all emit logs today, but they sit in each platform's native viewer with no retention, no aggregated search, no alerting. This dir holds the configuration + runbook for shipping all of those into one place.

## Vendor

**Default pick: Axiom** (https://axiom.co). Rationale:

| Vendor | Vercel native | Free tier | Setup time | Notes |
|---|---|---|---|---|
| **Axiom** | ✅ one-click Vercel integration | 500 GB/mo ingest, 30-day retention | ~5 min | APL query language; alert webhooks built-in |
| Better Stack (Logtail) | drain config | 1 GB/mo (small) | ~10 min | nicer UI, smaller free tier |
| Datadog | drain config | 14-day trial | ~20 min | full APM stack but pricey at scale |
| SigNoz | self-hosted | unlimited (you run it) | ~hours | OSS; only if we already operate it |

Going with Axiom. Switch by editing the URL/token in the Vercel/Railway drain step below — the JSON log shape we emit is vendor-agnostic.

## What the code already emits

The control plane uses structured one-line JSON via `console.log(JSON.stringify({level, route, msg, ...extra}))`. Drains pick up stdout/stderr as-is. Sites already wired:

- `apps/admin/app/api/internal/cluster-backups/route.ts` — emits `level=info|warn|error`, `op`, `flagged`, `platform`, `label`, `workflowRunId` per cluster-backup operation
- `apps/admin/app/api/cron/outbox-tick/route.ts` — already logs auth failures (will be augmented with per-row dispatch results when the outbox grows)
- `packages/workflows/src/provision-tenant.ts` — `[loadTenant]`, `[emailWelcome]` instrumentation (the latter records `to_present`, `to_value` for delivery debugging)
- WDK runtime — every workflow step boundary is one Vercel log line (`POST /.well-known/workflow/v1/{flow,step}`)

Data plane (Odoo) writes its native log lines (`module/level/timestamp/message`) to stdout, which is what we'll drain.

## Activation — what's left for the user

Each drain endpoint needs an account + token. I can't sign up for you (Anthropic safety rule). Once you have an Axiom account:

1. **Create a dataset** at https://axiom.co — name it `odoo-saas` (or any).
2. **Create an API token** with `Ingest` permission scoped to that dataset. Copy it.
3. **Paste back** to me with:
   - `AXIOM_DATASET=odoo-saas`
   - `AXIOM_INGEST_TOKEN=xaat-...`

I will then, in one turn:

```bash
# 1) Vercel — both apps. Drain UI is at:
#    https://vercel.com/<team>/<project>/settings/log-drains
# CLI is faster:
for app in admin portal; do
  vercel integrations install axiom --project=odoo-saas-$app
done
# OR via the Vercel API directly (avoids the Marketplace install dance):
# POST https://api.vercel.com/v2/integrations/log-drains
#   { name, type: "json", url: "https://api.axiom.co/v1/datasets/odoo-saas/ingest?...",
#     projectIds: [...], headers: { "Authorization": "Bearer <token>" } }

# 2) Railway — Project → Settings → Log Drains → New Drain
#    type: Datadog-compatible (Axiom impersonates), URL: https://api.axiom.co/v1/datasets/odoo-saas/ingest
#    headers: Authorization=Bearer <token>
# CLI:
railway add log-drain --type generic-webhook \
  --url https://api.axiom.co/v1/datasets/odoo-saas/ingest \
  --header "Authorization=Bearer $AXIOM_INGEST_TOKEN"

# 3) Fly — deploy the superfly/fly-log-shipper app on the same org
#    Doc: https://github.com/superfly/fly-log-shipper
flyctl launch --image flyio/log-shipper --name odoo-saas-log-shipper --org personal --copy-config --now
flyctl secrets set --app odoo-saas-log-shipper \
  ACCESS_TOKEN="$(flyctl tokens create org-read --org personal --expiry 8760h)" \
  ORG=personal \
  AXIOM_TOKEN="$AXIOM_INGEST_TOKEN" \
  AXIOM_DATASET="$AXIOM_DATASET"
```

## Alerts to configure once logs are flowing

Per HARDENING.md item 2, set Axiom monitors on these queries:

| Alert | APL query | Trigger | Channel |
|---|---|---|---|
| Vercel function errors > N/min | `['odoo-saas'] \| where level == 'error' \| where _source startswith 'vercel-' \| summarize count() by bin(_time, 1m)` | > 5/min | email/slack |
| Odoo CRITICAL | `['odoo-saas'] \| where _source =~ 'odoo' \| where message contains 'CRITICAL'` | any | email |
| pgBackRest backup non-zero exit | `['odoo-saas'] \| where _source =~ 'github-actions' \| where conclusion == 'failure' and workflow contains 'pgbackrest'` | any | email |
| Vercel cron.failed | `['odoo-saas'] \| where event == 'cron.failed'` | any | email |
| Restore drill failure | `['odoo-saas'] \| where workflow == 'pgBackRest restore drill' and conclusion == 'failure'` | any | email |

Alert config lives in Axiom's UI — there's no IaC for monitors at the free tier. If we ever need that, switch to Grafana Alerting on a self-hosted SigNoz or Loki.

## Rotation

Axiom ingest tokens don't expire by default. Rotate annually:

```bash
# Create a new token (Axiom UI → Settings → API Tokens → New)
# Update Vercel:
for app in admin portal; do
  vercel integrations update axiom --project=odoo-saas-$app --token=<new>
done
# Update Railway drain (UI is easier than CLI here; the existing drain edit accepts new headers)
# Update Fly log-shipper:
flyctl secrets set --app odoo-saas-log-shipper AXIOM_TOKEN=<new>
# Revoke the old token in Axiom UI.
```

See [[reference-railway-cli-v458-ssh-gotchas]] for the broader secrets-rotation pattern used in this repo.
