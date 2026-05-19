# Agentlab — environment runbook

## What it is

A Fly.io app + Postgres pair holding a daily masked refresh of the
production tenant data. Agents use it for bug repro; reviewers use it
for spec validation; preview environments (Phase 8 Implementation
Agent) clone it as their template DB.

Apps:
- `odoo-saas-odoo-agentlab` — Odoo worker (config: [`infra/fly/agentlab/fly.toml`](../fly/agentlab/fly.toml))
- `odoo-saas-odoo-agentlab-db` — Fly Postgres (not yet provisioned; see
  "First-time setup")

Workflow: [`.github/workflows/agentlab-daily-restore.yml`](../../.github/workflows/agentlab-daily-restore.yml).
Spec: [`docs/superpowers/specs/2026-05-16-agentlab-environment-design.md`](../../docs/superpowers/specs/2026-05-16-agentlab-environment-design.md).

---

## What's shipped vs. deferred

### Shipped in this PR

- Fly app config for `odoo-saas-odoo-agentlab`.
- `.github/workflows/agentlab-daily-restore.yml` — daily 02:00 UTC
  cron that wakes the app, pg_dumps staging tenants, restores into
  agentlab, runs the masking script, rotates the reviewer OTP, and
  writes an audit event.
- This runbook.

### Deferred (Phase 5b follow-ups, separate PRs)

- **Python masking pipeline.** `infra/agentlab/mask-prod-data.sh` is
  still a skeleton with TODO sections. The workflow runs it in
  warn-only mode today. Ship the Python implementation with unit
  tests for each per-column strategy before pointing the workflow at
  real production data.
- **Better Stack log drain wiring.** The agentlab app should ship logs
  with `tenant=agentlab` tagging; needs `BETTERSTACK_LOGS_TOKEN`
  (deferral item from the Phases 2–11 analysis).
- **Grafana dashboard.** Per-tenant panels filterable by wave (spec
  §6); needs Grafana Cloud account first.
- **Sample-row PII audit step.** Once masking ships, the workflow
  step that asserts no PII leaks needs the Python deny-list matcher.

---

## First-time setup

### 1. Provision the agentlab Postgres app

Manual one-off via `flyctl` (cannot live in a workflow because it's a
single-shot creation that has prompts):

```bash
flyctl postgres create \
  --name odoo-saas-odoo-agentlab-db \
  --org goliatt \
  --region iad \
  --vm-size shared-cpu-1x \
  --volume-size 5 \
  --initial-cluster-size 1
# Note the connection string and password printed at the end.
```

### 2. Deploy the agentlab Odoo app

```bash
flyctl apps create odoo-saas-odoo-agentlab --org goliatt
flyctl volumes create agentlab_data --app odoo-saas-odoo-agentlab \
  --region iad --size 5
flyctl deploy \
  --app odoo-saas-odoo-agentlab \
  --config infra/fly/agentlab/fly.toml \
  --dockerfile Dockerfile \
  --remote-only
```

### 3. Wire secrets

```bash
flyctl secrets set --app odoo-saas-odoo-agentlab \
  ADMIN_PASSWORD="$(openssl rand -base64 24)" \
  PGHOST=odoo-saas-odoo-agentlab-db.internal \
  PGPORT=5432 \
  PGUSER=postgres \
  PGPASSWORD="<from step 1>"
```

### 4. Add the workflow secrets to the repo

```bash
gh secret set AGENTLAB_DSN -R GoliattCo/odoo-custom \
  --body "postgresql://postgres:<pwd>@odoo-saas-odoo-agentlab-db.internal:5432/postgres"
gh secret set STAGING_PG_DSN -R GoliattCo/odoo-custom \
  --body "<staging pool DSN with read access>"
# CONTROL_PLANE_PG_DSN and FLY_API_TOKEN already exist.
```

### 5. Trigger the first restore manually

```bash
gh workflow run agentlab-daily-restore.yml \
  -R GoliattCo/odoo-custom \
  -f dry_run=true
gh run watch -R GoliattCo/odoo-custom $(gh run list -R GoliattCo/odoo-custom --workflow=agentlab-daily-restore.yml -L 1 --json databaseId --jq '.[0].databaseId')
```

Once dry-run passes, flip to `dry_run=false` for the real restore.

---

## Reviewer access

Reviewers and agents need browser + SSH access:

### Browser

URL: https://odoo-saas-odoo-agentlab.fly.dev/web/login

Credentials:
- Login: `reviewer@agentlab`
- Password: the OTP rotated by yesterday's restore. Retrieve via:
  ```bash
  flyctl secrets list --app odoo-saas-odoo-agentlab | grep AGENTLAB_REVIEWER_OTP
  ```
  (Secrets are write-only on Fly — actual value is only visible at
  the time of `secrets set`. The restore workflow logs the value as
  an `::notice::` you can retrieve from the GHA run log.)

### SSH

```bash
flyctl ssh console --app odoo-saas-odoo-agentlab
```

Agents authenticate via the same `FLY_API_TOKEN` they use everywhere
else; no separate credential.

---

## Daily operation

The cron runs at 02:00 UTC (= 21:00 Bogotá), wakes the machines via
`fly machines start`, restores fresh data, applies masking, rotates
the OTP, writes an audit event. Workflow timeout is 60 min; current
data volume completes in ~25 min.

To watch the live restore:

```bash
gh run watch -R GoliattCo/odoo-custom \
  $(gh run list -R GoliattCo/odoo-custom \
       --workflow=agentlab-daily-restore.yml -L 1 \
       --json databaseId --jq '.[0].databaseId')
```

To skip a day (e.g. ongoing incident on staging):

```bash
gh workflow disable agentlab-daily-restore.yml -R GoliattCo/odoo-custom
# ...
gh workflow enable agentlab-daily-restore.yml -R GoliattCo/odoo-custom
```

---

## Failure modes

| Symptom | Likely cause | First debug step |
|---|---|---|
| `pg_dump: error: connection to server failed` | `STAGING_PG_DSN` rotated; secret stale | Re-mint staging read-only credentials, `gh secret set` |
| `pg_restore: error: could not connect to database` | Agentlab Postgres app stopped / OOM | `flyctl status --app odoo-saas-odoo-agentlab-db` |
| masking script aborts mid-run | Implementation still skeleton; expected (warn-only) | Track in follow-up issue |
| `audit-event INSERT` fails | `saas_audit` schema not yet applied to control-plane | Apply [`infra/sql/saas-audit-event-schema.sql`](../sql/saas-audit-event-schema.sql) |
| OTP rotation fails after deploy | Fly machines didn't restart cleanly | `flyctl machines list --app odoo-saas-odoo-agentlab` + manual restart |
| Workflow times out (>60min) | Tenant volume exceeded sizing | Bump `timeout-minutes` in workflow OR split per-tenant matrix |

---

## Network policy

Agentlab is sensitive (it holds tenant data, even masked). Egress is
restricted to:

- `github.com` (pull addon code if needed)
- `api.anthropic.com` (LLM calls from agents running against agentlab)
- `*.fly.dev` (Fly internal routing)
- the staging Postgres endpoint (for the daily restore)

Configure via the Fly outbound firewall once Fly exposes it for
non-enterprise plans; until then, document the expected allow-list
in code review (see [`infra/fly/agentlab/fly.toml`](../fly/agentlab/fly.toml)
header for the explicit list).

---

## Related work

- Spec: [`docs/superpowers/specs/2026-05-16-agentlab-environment-design.md`](../../docs/superpowers/specs/2026-05-16-agentlab-environment-design.md)
- Masking allow-list: [`infra/agentlab/mask-allowlist.yml`](../agentlab/mask-allowlist.yml)
- Masking rules: [`infra/agentlab/masking-rules.yml`](../agentlab/masking-rules.yml)
- Audit table: [`saas_audit.event`](./saas-audit-event.md)
- Phase 8 dependency: Implementation Agent preview envs spawn from agentlab DB as a template.
