# infra/fly/preview

Scripts that spawn and manage **per-spec preview environments** for the
Implementation Agent (Phase 8 of the v7 roadmap).

See: `docs/superpowers/specs/2026-05-16-implementation-agent-design.md` §6.

## Files

- `spawn.sh` — provision a new preview app + Postgres + reviewer login.
- `seed.sh` — restore masked snapshot into the preview's tenant DB.
- `make-reviewer.sh` — create a one-time reviewer user in the preview tenant.
- `redeploy.sh` — rebuild the image from current branch and rolling-deploy.
- `destroy.sh` — destroy a preview app + its paired Postgres + DNS records.

## Naming

Apps: `odoo-saas-preview-spec-<NNN>` (NNN = GitHub issue/PR number).
URL:  `https://preview-<NNN>.<your-domain>` (wildcard cert on `preview-*`).
DB:   `preview_<NNN>` in the preview-Postgres-app.

## Limits

- Max **10 concurrent** preview envs org-wide (configurable). Overflow
  queues with an issue comment.
- Each preview is destroyed by `preview-cleanup.yml` when the PR merges,
  closes, or has been inactive ≥ 14 days.

## Cost

Approximately $1–8/preview/month with auto-stop machines. See spec §6.6.
