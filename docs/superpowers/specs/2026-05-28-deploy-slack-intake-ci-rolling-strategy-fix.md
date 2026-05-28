# Deploy slack-intake — drop pinned `--strategy rolling` from CI deploy

**Date:** 2026-05-28
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (follows §2.5 of `docs/2026-05-15-spec-driven-dev-plan.md`)
**Linked issue:** N/A — Wave 1 stabilization (CI workflow drift vs. local deploy.sh)
**Severity:** medium

---

## 1. Symptom

`.github/workflows/deploy-slack-intake.yml` fails on every push to `main`
that touches `agents/**` or `infra/fly/slack-intake/**`. The Deploy job
aborts with:

> could not create a fly.toml from any machines

The bot itself is already live (first deploy was done out-of-band during
the slack-intake rollout), so this only blocks CI-driven *updates*.

## 2. Repro

1. Push any change under `agents/**` to `main`.
2. Watch the **Deploy slack-intake → Deploy to Fly** job.
3. `flyctl deploy ... --strategy rolling` errors with "could not create a
   fly.toml from any machines".

**Reproduced on:** every push to `main` touching the trigger paths since
the workflow landed.

## 3. Affected tenants & severity

- **Tenants impacted:** none directly — slack-intake is an internal agent
  service, not a tenant-facing data-plane component.
- **Severity:** medium — CI cannot ship slack-intake updates; the bot can
  only be updated by hand via `infra/fly/slack-intake/deploy.sh`.
- **Workaround available?** yes — manual `deploy.sh` from a local checkout.

## 4. Root cause

`flyctl deploy --strategy rolling` requires an existing set of machines to
roll the new release into. A rolling deploy can't bootstrap from zero
machines, which is what produced the "could not create a fly.toml from any
machines" error during the first deploy. The same bug was already worked
around locally in `infra/fly/slack-intake/deploy.sh` during the rollout,
but the fix was never propagated to the CI workflow — classic config
drift between the local script and CI.

`.github/workflows/deploy-slack-intake.yml` — the Deploy step pins
`--strategy rolling` unconditionally.

## 5. Proposed fix

Drop the `--strategy rolling` flag and let flyctl pick its default: it
selects `immediate` on a first deploy (no machines yet) and `rolling` for
subsequent updates. This makes the workflow correct for both the
first-deploy and the steady-state-update cases.

```yaml
# before
flyctl deploy agents \
  --app odoo-saas-slack-intake \
  --config infra/fly/slack-intake/fly.toml \
  --dockerfile agents/Dockerfile \
  --remote-only \
  --strategy rolling

# after
flyctl deploy agents \
  --app odoo-saas-slack-intake \
  --config infra/fly/slack-intake/fly.toml \
  --dockerfile agents/Dockerfile \
  --remote-only
```

## 6. Regression test

CI itself is the test:

- The **Deploy slack-intake → Deploy to Fly** job succeeds on the next
  push to `main` that touches the trigger paths (and on `workflow_dispatch`).
- The `/healthz` smoke check still returns 200 after the deploy.

## 7. Rollout

- Severity = medium → ride the next normal wave (this PR).
- No feature flag — CI workflow change only.
- Note: `infra/fly/slack-intake/deploy.sh` still pins `--strategy rolling`;
  it works today because the app already has machines, but it carries the
  same latent first-deploy bug. Left out of this single-file PR; worth a
  follow-up to align the manual script with this fix.
