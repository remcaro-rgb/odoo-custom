# Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Linked spec:** none (Phase 1 is process bootstrap; the master plan §11 is the source of truth).
**Goal:** Ship the spec-workflow enforcement layer so all subsequent phases run inside the discipline they require.
**Architecture:** GitHub-native — templates as markdown, ADRs as markdown, CI gates as GHA workflows. No new services.
**Tech stack:** GitHub Actions, `gh` CLI, GitHub Environments, CODEOWNERS.

---

## Chunk 1: Templates, ADRs, CODEOWNERS, PR template

### Task 1: Land the spec + plan templates

**Files:**
- Create: `docs/superpowers/specs/_TEMPLATE-design.md` ✅ delivered
- Create: `docs/superpowers/specs/_TEMPLATE-fix.md` ✅ delivered
- Create: `docs/superpowers/plans/_TEMPLATE.md` ✅ delivered

- [x] **Step 1: Verify the templates render correctly in GitHub**

```bash
gh repo view --web
# Browse to docs/superpowers/specs/_TEMPLATE-design.md
```

Expected: markdown renders cleanly; section numbering matches §2.4 of main plan.

- [x] **Step 2: Add a CONTRIBUTING.md pointer to these templates** (2026-05-19: `CONTRIBUTING.md` created)

```bash
cat >> CONTRIBUTING.md <<'EOF'

## Writing a spec

For new features → copy `docs/superpowers/specs/_TEMPLATE-design.md`.
For bug fixes → copy `docs/superpowers/specs/_TEMPLATE-fix.md`.
For implementation steps → copy `docs/superpowers/plans/_TEMPLATE.md`.

The `spec-required` CI check enforces that every non-trivial PR links to a spec.
EOF
```

Expected: a section in CONTRIBUTING.md pointing devs at the templates.

### Task 2: Land the ADR folder

**Files:**
- Create: `docs/adr/README.md` ✅ delivered
- Create: `docs/adr/0001-trunk-based-with-waves.md` ✅ delivered
- Create: `docs/adr/0002-cross-platform-parity.md` ✅ delivered
- Create: `docs/adr/0003-log-drain-better-stack.md` ✅ delivered

- [ ] **Step 1: Review the three ADRs as a team**

ADRs are decisions. They need owner sign-off. Schedule 15 min with the team
to either accept as-is or amend.

Expected: all three move from `Status: Accepted` (their default) to truly
team-accepted, or amended in-place.

- [ ] **Step 2: Tag ADR 0001 reviewers with @ in the PR body**

The first ADR sets the trunk-based-with-waves direction — make sure
prod-deployers and security-leads see it.

### Task 3: Configure CODEOWNERS

**Files:**
- Modify: `.github/CODEOWNERS` ✅ scaffold delivered

- [x] **Step 1: Replace `@your-org/*` placeholders with real team slugs** (2026-05-19: rewritten to `@GoliattCo/*` after repo transfer from `remcaro-rgb` → `GoliattCo`)

```bash
# Find every placeholder
grep -n '@your-org' .github/CODEOWNERS
```

Expected: a list of lines to edit. Replace each `@your-org/<team>` with your
real org slug and team name.

- [x] **Step 2: Create the GitHub teams if they don't exist** (2026-05-19: 8 teams created in `GoliattCo` org with `@remcaro-rgb` as maintainer of each)

```bash
gh api orgs/<org>/teams -X POST -f name=maintainers
gh api orgs/<org>/teams -X POST -f name=security-leads
gh api orgs/<org>/teams -X POST -f name=prod-deployers
gh api orgs/<org>/teams -X POST -f name=agent-team
gh api orgs/<org>/teams -X POST -f name=senior-engineers
# Per-addon owner teams as needed
gh api orgs/<org>/teams -X POST -f name=club-addon-owners
gh api orgs/<org>/teams -X POST -f name=accounting-addon-owners
gh api orgs/<org>/teams -X POST -f name=colombia-localization
```

Expected: all teams created with 0 members (you add humans next).

- [x] **Step 3: Add team members** (2026-05-19: `@remcaro-rgb` set as maintainer of all 8 teams; second-human N=2 deferred to first hire)

For each team, add the right humans via GitHub web UI or
`gh api orgs/<org>/teams/<team>/memberships/<user> -X PUT`.

Expected: every team has ≥ 1 member (use repo `maintainers` as a fallback
for unstaffed teams).

- [x] **Step 4: Verify CODEOWNERS parses correctly** (2026-05-19: `gh api repos/GoliattCo/odoo-custom/codeowners/errors` → `{"errors":[]}`)

```bash
gh api repos/<org>/<repo>/codeowners/errors
```

Expected: empty errors array. If errors appear, fix the patterns.

### Task 4: Land the PR template

**Files:**
- Create: `.github/PULL_REQUEST_TEMPLATE.md` ✅ delivered

- [ ] **Step 1: Open a test PR to verify the template renders**

```bash
git checkout -b chore/test-pr-template
echo "# test" > /tmp/dummy.md
git add /tmp/dummy.md
git commit -m "test"
git push origin chore/test-pr-template
gh pr create --title "test" --body ""
```

Expected: the PR body is pre-filled with the template. Close the PR.

---

## Chunk 2: CI enforcement workflows

### Task 5: Land spec-required workflow

**Files:**
- Create: `.github/workflows/spec-required.yml` ✅ delivered

- [ ] **Step 1: Push the workflow and watch a no-spec PR fail**

```bash
git checkout -b test/spec-required-failure
echo "# test" > custom-addons/dummy/__manifest__.py
git add custom-addons/dummy/__manifest__.py
git commit -m "test no-spec failure"
git push origin test/spec-required-failure
gh pr create --title "test no-spec" --body "no spec linked"
```

Expected: `spec-required` CI check fails with a clear error message
("PR touches addons/infra/workflows/Dockerfile but no 'Spec:' line found").

- [ ] **Step 2: Verify the spec-exempt label bypass**

```bash
gh pr edit <number> --add-label spec-exempt
# Re-run the check
gh pr checks <number> --watch
```

Expected: check now passes with a notice ("PR carries spec-exempt label").

- [x] **Step 3: Add `spec-required` to required status checks on `main`** (2026-05-19: `Spec link present` included in classic protection on main)

In GitHub repo settings → Branches → main → Branch protection rules:
- Require status checks to pass before merging
- Require these checks: `Spec link present`

Expected: PRs cannot merge to main without this check passing.

### Task 6: Land agent-guardrails workflow

**Files:**
- Create: `.github/workflows/agent-guardrails.yml` ✅ delivered

- [x] **Step 1: Create the AGENTS_ENABLED repo variable** (2026-05-19: set to `true`)

```bash
gh variable set AGENTS_ENABLED --body "true"
```

Expected: variable visible in repo settings.

- [ ] **Step 2: Test the kill-switch path**

Temporarily set `AGENTS_ENABLED=false` and open a PR from an `agent/` branch.

Expected: `agent-guardrails` check fails immediately with kill-switch error.

Reset:
```bash
gh variable set AGENTS_ENABLED --body "true"
```

- [x] **Step 3: Add `agent-guardrails` to required status checks** (2026-05-19: included in main protection and agent/spec-* ruleset)

Same as Step 3 of Task 5, for `Agent guardrails` check.

Expected: agent-branch PRs cannot merge without this check passing.

---

## Chunk 3: Branch protection

### Task 7: Configure branch protection on `main`

- [x] **Step 1: Required status checks** (2026-05-19: 6 checks set via classic protection, cross-platform deploy jobs excluded — push-only triggers)

In settings → Branches → main:
- Required: `Spec link present`, `Agent guardrails`, `Build Odoo image`,
  `Build Postgres image`, `Build Traefik image`, `saas_tenant_gate test suite`,
  `Cross-platform parity gate`.

- [x] **Step 2: Require linear history** (2026-05-19: `required_linear_history=true`)

- [ ] **Step 3: Require signed commits** (deferred for `main`: local signing not set up; active on `agent/spec-*` ruleset since no commits exist there yet)

- [ ] **Step 4: Require ≥ 1 CODEOWNERS approval** (deferred: would block solo operator since CODEOWNERS auto-routes to the author. Flip when headcount >= 2)

- [x] **Step 5: Restrict pushes** (2026-05-19: classic protection `restrictions.teams=[prod-deployers]`)

### Task 8: Configure branch protection on `agent/spec-*`

- [x] **Step 1: Pattern-based rule for `agent/spec-*`** (2026-05-19: ruleset id 16603187, `refs/heads/agent/spec-*`)

- [x] **Step 2: Refuse force-push and history rewrite** (2026-05-19: ruleset rules `non_fast_forward` + `deletion`)

(Required for the v5 reporter-ping policy — no force-push circumvention.)

- [x] **Step 3: Require signed commits** (2026-05-19: ruleset rule `required_signatures`)

- [x] **Step 4: Require status checks** (2026-05-19: 7 checks via ruleset — 6 main checks + `Spec quality checks`)

Same as for `main`, plus the spec-quality workflow.

---

## Verification

End-of-phase checklist:

- [ ] All Phase 1 sub-issues in `docs/2026-05-16-github-issues-roadmap.md` are closed.
- [ ] An intentionally-malformed PR (touches addons, no spec link) fails CI.
- [ ] An intentionally-malformed PR (agent branch, > 400 LOC) fails CI.
- [ ] `AGENTS_ENABLED=false` blocks every agent PR.
- [ ] Branch protection prevents direct push to `main` and to `agent/spec-*`.
- [ ] One real spec-linked PR merges cleanly via the normal path.
- [ ] Retro ADR: write `docs/adr/0004-phase-1-retrospective.md` capturing
  what was learned during Phase 1 setup.

Expected total time: **1 week** for a focused engineer + 30 min/day from each
reviewer who has to sign off on team membership and ADRs.
