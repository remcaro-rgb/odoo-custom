# GitHub-Admin TODOs (AFK Phase 1 — operator clicks)

These are the GitHub-admin actions that the 2026-05-16 AFK Phase 1 plan
requires before agentic execution can actually run. They cannot be done
from CLI or by Claude; they need browser clicks in github.com settings.

This is a one-time setup; once done, agents and the CI pipelines can
operate autonomously per their charters.

---

## 1. Create GitHub teams (under `remcaro-rgb` org/user namespace)

Today the data plane is owned by `remcaro-rgb` (personal account). To
support the AFK plan's per-team CODEOWNERS layout, you eventually need a
GitHub organization with these teams:

| Team | Members | Purpose |
|---|---|---|
| `maintainers` | you + future hires | Catch-all approver for `*`. |
| `security-leads` | you (+ future SOC) | `/infra/`, `/custom-addons/saas_*/`, agent charters, mask configs. N=2 on critical paths. |
| `prod-deployers` | you (+ future SRE) | `/infra/`, `Dockerfile`, `railway.toml`. Reviewer on `prod-rollout` Environment. |
| `agent-team` | you (+ future ML/RPA) | `/agents/` runtime. |
| `senior-engineers` | you (+ tech leads) | `/docs/adr/`. ADRs require senior approval. |
| `club-addon-owners` | TBD | `/custom-addons/club_*/` |
| `accounting-addon-owners` | TBD | `/custom-addons/account_*/`, `/co_*/` |
| `colombia-localization` | TBD | `/jorels-addons/` |

**Note:** until the team is more than 1 person, CODEOWNERS just lists
`@remcaro-rgb` for every path (current state). The team-based slicing is
a forward-looking layout; flip the entries when the second hire lands.

**Action:** github.com → Profile picture → "Your organizations" →
"New organization". Add the teams above as empty teams. Then update
`.github/CODEOWNERS` from `@remcaro-rgb` → `@<org>/<team>` per the
"future:" comments.

---

## 2. Branch protection on `main`

github.com → Repo → Settings → Branches → "Add branch protection rule":

- Branch name pattern: `main`
- ☑ Require a pull request before merging
- ☑ Require approvals (1)
- ☑ Dismiss stale pull request approvals when new commits are pushed
- ☑ Require review from Code Owners
- ☑ Require status checks to pass before merging
  - Pick: `Lint + typecheck + unit tests` (from `test-control-plane.yml`)
  - Pick: `Vercel – odoo-saas-admin`
  - Pick: any spec-required / agent-guardrails workflows once they land
- ☑ Require branches to be up to date before merging
- ☑ Do not allow bypassing the above settings (incl. for admins) — recommended
- ☐ Allow force pushes — leave OFF

Repeat for `agent/spec-*` pattern (Spec Generator's branch namespace) with:
- Require status checks: `spec-quality` workflow
- Allow agent-team to push directly (no PR required for their own spec-namespaced branches)

---

## 3. Repo-level variable `AGENTS_ENABLED`

github.com → Repo → Settings → Secrets and variables → Actions →
Variables tab → "New repository variable":

- Name: `AGENTS_ENABLED`
- Value: `false`

This is the kill switch. `agent-guardrails.yml` checks this; when
`false`, all agent workflows refuse to run. Flip to `true` only after
all the team/environment setup is complete and you're ready to let
agents act.

---

## 4. GitHub Environments

github.com → Repo → Settings → Environments → "New environment":

| Environment | Required reviewers | Purpose |
|---|---|---|
| `prod-rollout` | 1× prod-deployers | Normal prod promotions (promote-to-prod.yml). |
| `prod-rollback` | 2× prod-deployers (one must NOT be the rollback initiator) | Emergency rollback (rollback-prod.yml). |
| `prod-hotfix` | 2× prod-deployers | Critical hotfixes that skip the normal soak window. |
| `prod-railway` | 1× prod-deployers | Railway-specific deploys (data plane). |
| `prod-fly` | 1× prod-deployers | Fly-specific deploys (data plane). |

For each env: pick the reviewer team(s), tick "Required reviewers", set
wait timer to 0 unless you want a forced soak (recommended: 0 for non-
rollout, 5 min on prod-rollout).

---

## 5. Secrets to provision (Actions tab → Secrets)

Some workflows will need these to run. Most are placeholder until the
underlying integration is needed:

| Secret | Used by | Source |
|---|---|---|
| `RAILWAY_TOKEN` | `ci.yml` deploy-railway job | Railway → Account → Tokens |
| `RAILWAY_ODOO_SERVICE_ID` | same | Railway → Project → Service → Settings |
| `FLY_API_TOKEN` | `ci.yml` deploy-fly job | `fly auth token` |
| `NEON_API_KEY` | future integration-test layer (item 16) | https://console.neon.tech/app/settings/api-keys |
| `E2E_PREVIEW_URL` | `test-control-plane.yml` e2e job | latest preview URL from Vercel (rotated per PR? auto-pulled from Vercel webhook? — open question) |
| `E2E_OPERATOR_CLERK_TOKEN` | same | Clerk dev instance, see [open question 7 in operator-ui spec](superpowers/specs/2026-05-17-license-management-ui-design.md#10-open-questions) |
| `E2E_NON_OPERATOR_CLERK_TOKEN` | same | same |

Already configured: nothing in the data plane today; the existing CI
(`ci.yml`) doesn't actually call deploy jobs without these.

---

## Done-when checklist

- [ ] Teams created (or single-user CODEOWNERS accepted)
- [ ] Branch protection rule on `main` with code-owner review required
- [ ] `AGENTS_ENABLED=false` set as repo variable
- [ ] 5 environments created with required reviewers
- [ ] At minimum `NEON_API_KEY` + `E2E_*` Clerk tokens added if you want
      integration tests + Playwright to actually run in CI
- [ ] Flip `AGENTS_ENABLED=true` only after all of the above lands

When everything above is done, the agent-guardrails workflow stops
blocking and the AFK plan's autonomous-agent execution becomes possible.
