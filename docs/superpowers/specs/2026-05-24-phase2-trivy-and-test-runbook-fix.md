# Phase 2 — add `trivy-scan` Gate-1 job + `writing-addon-tests.md` runbook

**Date:** 2026-05-24
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (Phase 2 of `docs/2026-05-15-spec-driven-dev-plan.md` — items P2.4 trivy half, P2.10)
**Linked issue:** N/A — Phase 2 hardening continuation (companion to PR #39)
**Severity:** medium

---

## 1. Symptom

Two Phase 2 gaps remain after PR #39 (lint-xml + lint-odoo-manifest + gitleaks):

1. **CVE scan for filesystem + Dockerfile (P2.4's other half).** PR #39
   shipped gitleaks (secrets). The other half of P2.4 is `trivy fs` —
   scan Python deps, Dockerfile base images, and on-disk configs for
   known CVEs. Today a `requirements.txt` pinning a known-vulnerable
   library, or a Dockerfile `FROM` that pulled in an unpatched base,
   reaches `main` without warning.

2. **No addon-test-writing reference (P2.10).** Anyone adding tests to
   a new addon has to read three existing test suites + the Odoo docs
   to figure out the conventions (TransactionCase vs HttpCase, tag
   semantics, fixture patterns, masking, what to mock). A single
   runbook would cut the onboarding friction.

## 2. Repro

1. Push a PR that bumps `requirements.txt` to a known-CVE library
   (e.g. `requests<2.31.0` for CVE-2023-32681). CI passes — no scan.
2. Open a fresh addon and try to add tests. There's no canonical
   reference; one ends up copying patterns from `saas_tenant_gate`
   without knowing which are mandatory vs idiosyncratic.

**Reproduced on:** every PR until now (no trivy gate); every new
addon test author until now (no runbook).

## 3. Affected tenants & severity

- **Tenants impacted:** none directly (PR-time gates + docs).
- **Severity:** medium for trivy (CVE class), low for the runbook
  (developer-experience).

## 4. Root cause

Both items are explicit Phase 2 roadmap deliverables that weren't
shipped in the initial push. Today's session's audit confirms them
as the remaining gaps (alongside P2.5 / P2.6 / P2.8 — separate PRs).

## 5. Proposed fix

### Job — `trivy-scan` in `.github/workflows/ci.yml`

Use the official `aquasecurity/trivy-action@0.28.0` action. Scan the
filesystem on every PR + push to main. Fail on HIGH or CRITICAL CVEs.
`trivy.yaml` config can ignore false positives we accept (none today).

```yaml
trivy-scan:
  name: Trivy filesystem CVE scan
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: aquasecurity/trivy-action@0.28.0
      with:
        scan-type: fs
        scan-ref: .
        severity: HIGH,CRITICAL
        exit-code: '1'
        ignore-unfixed: true
        format: table
```

`ignore-unfixed: true` — many CVEs against Debian base images have
no fix available yet; not actionable on the PR, surfaces as noise.
Re-enable when the no-fix backlog becomes manageable.

### Runbook — `docs/runbooks/writing-addon-tests.md`

A single ~400-line markdown reference covering:

- The Odoo test taxonomy: `TransactionCase`, `SavepointCase`,
  `HttpCase`, `SingleTransactionCase`, `BaseCase`. Which to use when.
- Tag semantics: `post_install` vs `at_install`, why our HttpCase
  suite uses `--test-tags '/<addon>'`, the trap from
  https://github.com/odoo/odoo/commit/... (post_install-only tags
  silently match zero tests under `--test-tags '/x,-post_install'`).
- Where to put tests: `tests/__init__.py` import discipline (must
  be a single combined `from . import a, b, c` line for ruff `I001`
  cleanliness — see Tier-7 bug #1 on `remcaro-rgb/Odoo-saas-agents`
  commit `4b80156`).
- Fixture patterns: setUp, cleanups, `self.env.ref` lookups.
- Mocking strategy: `unittest.mock.patch` on Odoo registry methods;
  don't reach into transport.
- Common pitfalls: `--stop-after-init` doesn't run HttpCase tests;
  `--test-enable` only runs at-install-tagged tests unless tagged
  otherwise; `self.env['model'].browse(0)` returns an empty
  recordset, not an error.
- How to run locally: docker compose + the env vars our CI uses;
  `pytest custom-addons/<addon>/tests/` doesn't work — Odoo's test
  runner is the only sound path.
- Adding the test file: spec template §6, the import line in
  `tests/__init__.py`, the manifest's `external_dependencies`.

## 6. Regression test

CI itself is the test:
- `trivy-scan` job appears in PR #40's check rollup; passes on the
  unchanged tree (no HIGH/CRITICAL CVEs).
- The runbook lives at `docs/runbooks/writing-addon-tests.md` and is
  linked from `docs/runbooks/README.md`.

## 7. Rollout

- Severity = medium → ride the next normal wave.
- No feature flag — CI + docs additions.
- Expected outcomes:
  - `trivy-scan` SUCCESS on PR #40 against the unchanged tree.
  - The new runbook is searchable + grep-able in repo search.
