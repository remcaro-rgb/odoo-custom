# 0004. Phase 1 retrospective — spec workflow enforcement bootstrap

**Date:** 2026-05-19
**Status:** Accepted

## Context

Phase 1 of the [spec-driven dev plan](../2026-05-15-spec-driven-dev-plan.md)
shipped the foundation layer: spec/plan/fix-brief templates, ADR scaffolding,
CODEOWNERS, the PR template, and six GHA enforcement workflows
(`spec-required`, `agent-guardrails`, `spec-quality`, `promote-to-prod`,
`rollback-prod`, `preview-cleanup`). Per §11 of the master plan, every phase
must close with a retrospective ADR capturing what was actually learned.

## Decision

Record the following as the Phase 1 outcome and let it inform Phase 2 onward.

### What landed

- **Templates:** `_TEMPLATE-design.md`, `_TEMPLATE-fix.md`, plans `_TEMPLATE.md`.
- **ADRs:** 0001 trunk-based-with-waves, 0002 cross-platform parity, 0003
  Better Stack log drain — all in `Accepted` state.
- **CODEOWNERS:** team-based layout under `@GoliattCo/*` slugs after the
  2026-05-19 org migration. Eight teams created
  (`maintainers`, `security-leads`, `prod-deployers`, `agent-team`,
  `senior-engineers`, `club-addon-owners`, `accounting-addon-owners`,
  `colombia-localization`); each has `@remcaro-rgb` as maintainer and push
  access to the repo (`prod-deployers`: maintain). Validated via
  `gh api repos/GoliattCo/odoo-custom/codeowners/errors` → `{"errors":[]}`.
- **Org migration:** `remcaro-rgb/odoo-custom` transferred to
  `GoliattCo/odoo-custom`. Operational references in `.github/SECRETS.md`,
  `infra/runbooks/move-tier.md`, and recent session docs updated to the new
  path. March-dated specs/plans intentionally left referencing the old
  owner as point-in-time records.
- **PR template:** `.github/PULL_REQUEST_TEMPLATE.md` with the v6 5-item
  CODEOWNERS checklist including the v5 reporter-ping clause (item 4).
- **CI gates (all parse-clean under strict pyyaml):**
  - `spec-required.yml` — blocks PRs that touch `custom-addons/`, `infra/`,
    workflows, or `Dockerfile` without a `Spec:` line, modulo
    `spec-exempt` label.
  - `agent-guardrails.yml` — enforces 12 hard rules on `agent/spec-*`
    branches (≤ 400 LOC, no infra edits, signed commits, test count must
    not shrink, spec-correction prefix audit, kill switch via
    `AGENTS_ENABLED`).
  - `spec-quality.yml` — template completeness, tenancy impact, open
    questions, regression-test sketches.
  - `promote-to-prod.yml`, `rollback-prod.yml`, `preview-cleanup.yml`
    — operational workflows referenced by later phases.
- **Kill switch:** repo variable `AGENTS_ENABLED=true` set; flipping to
  `false` halts all agent CI immediately.
- **CONTRIBUTING.md:** new file pointing developers at the templates and
  explaining the `spec-required` and `agent-guardrails` gates.
- **Branch protection on `main`** (classic protection): 7 required
  status checks (`Spec link present`, `Agent guardrails`, `Spec quality
  checks`, `Build Odoo image`, `Build Postgres image`, `Build Traefik
  image`, `saas_tenant_gate test suite`), `strict=true` (branch must be
  up to date), `enforce_admins=true` (no admin bypass),
  `required_linear_history`, `required_signatures=true` (added
  2026-05-19 after item 6), `allow_force_pushes=false`,
  `allow_deletions=false`, `required_conversation_resolution=true`.
  Direct-push restriction scoped to the `prod-deployers` team. The
  cross-platform deploy/parity jobs are intentionally omitted from
  required checks — they only run on push to main, not on PRs (would
  never report a status). `Spec quality checks` was added to the
  required list after item 3 removed its paths filter so it triggers
  on every PR (SKIPPED on non-agent branches still counts as pass).
- **Ruleset for `agent/spec-*`** (id `16603187`, enforcement `active`):
  blocks deletion and non-fast-forward (no force-push, no history
  rewrite — satisfies §5.4.3.1 v5 invariant), requires signed commits
  (per §5.4.3.1), requires the 6 main checks plus `Spec quality
  checks`, and routes through PR review with conversation resolution.

### What did not land, and why

- **`N=2` enforcement deferred** — see next bullet for why this stays
  off until the first hire even though structurally it could be enabled
  today.
- **`N=2` enforcement for security-sensitive paths.** Teams exist with the
  right structure, but `@remcaro-rgb` is currently the only member of
  every team. Enabling "Required approving reviews: 2" in branch
  protection (or a path-scoped Ruleset over `saas_tenant_gate/security/`
  and `agents/charters/`) would permanently block all PRs until the
  second human joins. Defer activation to first team hire; teams already
  carry the right shape.

### What we learned

- **YAML strictness bites quietly.** Two of the six workflows
  (`spec-required.yml`, `preview-cleanup.yml`) parsed in GitHub Actions
  but failed strict pyyaml — an unquoted colon in a step `name:` and a
  shell-style `\` line continuation that dedented out of a YAML block
  scalar. Both fixed during this phase. Add a `yamllint`/`actionlint`
  pre-commit hook in Phase 2 so future drift is caught locally.
- **CODEOWNERS placeholders aren't the only thing to grep for.** The
  pre-migration scaffold used `@remcaro-rgb` directly with `@your-org/*`
  only as documentation comments — the Phase 1 plan's "replace `@your-org`"
  step was a no-op against that file. After the GoliattCo migration the
  comments were the only useful artifact: they encoded the intended team
  layout, which made the rewrite a mechanical replacement rather than a
  fresh design pass.
- **`gh repo transfer` does not exist.** The repo-transfer subcommand
  isn't in the gh CLI; transfer must go through
  `gh api repos/<old>/<repo>/transfer -X POST -f new_owner=<new>`. API
  returns `202 Accepted` with the body still showing the old owner —
  verify the move by polling `gh api repos/<new>/<repo>` rather than
  trusting the immediate response.
- **Phase 1 is mostly process, but the YAML still needs to compile.**
  Two-thirds of execution time went to verifying the artefacts, not
  creating new ones. Future phases should budget time for activation
  (variable creation, label seeding, branch-protection clicks) on top of
  artefact authoring.

## Consequences

**Positive.**
- All future PRs touching addons/infra/workflows are gated by CI on a
  spec link.
- The kill switch is live: `gh variable set AGENTS_ENABLED --body false`
  stops all agent activity in one command.
- Subsequent phases can rely on the templates, ADR folder, and CODEOWNERS
  surface being present and well-formed.

**Negative.**
- Team-based ownership is structurally present but functionally
  single-member. Security-sensitive paths route to `@GoliattCo/security-leads`,
  which has only `@remcaro-rgb` until the first hire — so the intended
  N=2 approval rule must remain disabled in branch protection or every
  PR blocks.
(Both former gaps closed in the same-day follow-up batch — see
"Same-day follow-ups (items 1-6)" below.)

## Same-day follow-ups (items 1-6)

The original list of deferrals from this ADR's first draft was audited
for feasibility in the same session. Six items were viable solo and
were executed in order:

1. **SSH commit signing** — dedicated ed25519 key generated
   (`~/.ssh/git_signing_ed25519`), `git config --global gpg.format ssh`,
   `commit.gpgsign=true`, `tag.gpgsign=true`, allowed-signers file
   populated. Local verification shows new commits report
   `%G? = G` (good signature, trusted). GitHub-side registration of
   the signing key still pending the operator running
   `gh auth refresh -s admin:ssh_signing_key` and `gh ssh-key add
   ~/.ssh/git_signing_ed25519.pub --type signing`.
2. **yamllint + actionlint** — `.yamllint.yml`, `.pre-commit-config.yaml`,
   and `.github/workflows/lint-workflows.yml` added. CONTRIBUTING.md
   documents the local install path. The very first actionlint run
   surfaced a latent bug: `promote-to-prod.yml` `notify` job referenced
   `needs.preflight.outputs.target_sha` without declaring `preflight`
   in its `needs:` list; fixed in the same commit.
3. **`Spec quality checks` always-runs** — paths filter removed from
   `on:`; existing job-level `if:` continues to skip non-agent
   branches. The check now reports a status on every PR (SKIPPED
   counts as pass) and is added to `main`'s required list.
4. **Protection-drift audit** — initial design tried to read live
   branch protection from the runner, which is impossible:
   `GITHUB_TOKEN` cannot access that endpoint and there is no workflow
   permission scope that grants it. Redesigned around a committed
   source-of-truth at `.github/required-checks.yml`. The workflow
   audits committed-config-against-job-names; a separate script
   `infra/scripts/check-protection-drift.sh` does live-vs-committed
   with a personal admin token. Today's run reports OK.
5. **Verification probes** — see next section.
6. **`required_signatures: true` on `main`** — enabled via
   `POST /branches/main/protection/required_signatures`. PR #1 is
   still `MERGEABLE` because squash-merges via the GitHub web UI/API
   are signed by the `web-flow` key. Future direct pushes of unsigned
   commits to `main` will be rejected.

## Verification probes (2026-05-19)

PR #1 served as the verification harness for the gates:

- **Spec link present — failure path:** First run reported `FAILURE`. PR #1's
  body links a *plan* (`docs/superpowers/plans/...`) rather than a *spec*
  (`docs/superpowers/specs/...-design.md`); the workflow regex correctly
  rejected the plan-only reference. Live evidence that the gate enforces
  the design intent.
- **Spec link present — `spec-exempt` bypass:** Adding the `spec-exempt`
  label re-triggered the workflow and the check flipped to `SUCCESS`. This
  is the designed bypass for process-bootstrap PRs that legitimately have
  no spec (Phase 1 is itself the spec-workflow bootstrap, so it qualifies).
- **`Agent guardrails` kill-switch:** Workflow logic verified by inspection
  ([agent-guardrails.yml step 'Kill-switch check']) — fails fast if the
  repo variable `AGENTS_ENABLED` is anything other than the literal string
  `true`. Live-toggle test deferred: requires pushing an `agent/*` branch,
  blocked by sandbox push-policy on this session. Run manually with:
  `gh variable set AGENTS_ENABLED --body false`, open an `agent/foo/bar`
  PR, observe `Agent guardrails: FAILURE`, then reset.

## Follow-ups (tracked separately)

1. Register the SSH signing key on GitHub
   (`gh auth refresh -s admin:ssh_signing_key && gh ssh-key add ~/.ssh/git_signing_ed25519.pub --type signing`).
   Until done, signed commits in this session show "Unverified" on
   github.com (the signature is cryptographically valid, GitHub just
   doesn't know whose key it is).
2. Re-point external systems still trusting the old GitHub repo path:
   GHA OIDC subject claims in Vercel/Fly/Railway
   (sub: `repo:GoliattCo/odoo-custom:*`), Vercel project Git connection,
   webhooks. Audit during Phase 2 setup.
3. When first hire lands:
   - Flip `required_pull_request_reviews.required_approving_review_count`
     from 0 → 1 on `main`.
   - Flip `require_code_owner_reviews` to `true`.
   - For paths needing N=2 (`saas_tenant_gate/security/**`,
     `agents/charters/**`), add a path-scoped Ruleset with
     `required_approving_review_count: 2`.
4. Live-run the `Agent guardrails` kill-switch probe (requires push of
   a temporary `agent/*` branch; logic verified by inspection today).
5. Design a PR-safe dry-run version of `Cross-platform parity gate` so
   it can become a required check on `main` PRs without actually
   deploying to Railway/Fly staging on every PR.
6. **HttpCase test suite step.** The `saas_tenant_gate test suite` job
   currently runs with `--test-enable --test-tags '/saas_tenant_gate,-post_install'`
   to exclude HttpCase tests, because `--stop-after-init` never starts
   the HTTP server (`'PreforkServer' object has no attribute 'httpd'`).
   Add a second job in `ci.yml` that starts Odoo without
   `--stop-after-init`, runs the `post_install` HttpCase suite via
   `url_open`, and sends `SIGTERM` after tests pass. Until then,
   `TestTelemetry` is verified locally only.
