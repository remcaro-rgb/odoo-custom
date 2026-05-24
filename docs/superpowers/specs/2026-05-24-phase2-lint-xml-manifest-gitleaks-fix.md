# Phase 2 Gate-1 hardening — add `lint-xml`, `lint-odoo-manifest`, `gitleaks-scan`

**Date:** 2026-05-24
**Author:** Manuel Caro
**Status:** In Review
**Spec type:** fix-brief (Phase 2 of `docs/2026-05-15-spec-driven-dev-plan.md` — items P2.2, P2.3, P2.4)
**Linked issue:** N/A — sharpens existing Gate-1 quality bars
**Severity:** medium (catches real bugs that today only surface at install / deploy time)

---

## 1. Symptom

Gate-1 (`.github/workflows/ci.yml`) catches Python lint via ruff +
bandit + agentlab masking + builds + addon tests. Three classes of
defect can land on `main` because Gate-1 doesn't check for them:

1. **Malformed XML in `custom-addons/**/*.xml`** — Odoo only catches
   parse errors at module install time (i.e. after the build job
   succeeds, never on the PR).
2. **Malformed Odoo `__manifest__.py`** — same: only surfaces when
   Odoo tries to load the module.
3. **Committed secrets in a PR diff** — no scan today. A leaked GitHub
   token, AWS key, or `OPENCODE_SERVER_PASSWORD` would be merged before
   anyone noticed.

## 2. Repro

1. Push a PR that adds a malformed XML view (missing closing tag).
2. CI passes Gate-1 (no XML linter); the build job's `odoo --init`
   crashes on install with a cryptic XML parse error.
3. Same for `__manifest__.py` with a syntax error or missing required
   key.
4. Same for a `.env` file or hardcoded API key — no warning.

**Reproduced on:** every PR until now.

## 3. Affected tenants & severity

- **Tenants impacted:** none directly — these are PR-time gates, not
  tenant-runtime.
- **Severity:** medium. Each prevents a class of bug that costs a full
  Docker-build cycle (5–10 min) to catch today.
- **Workaround:** manual review.

## 4. Root cause

Phase 2 roadmap (`docs/2026-05-15-spec-driven-dev-plan.md` §Phase 2)
specifies these as items P2.2, P2.3, P2.4. They weren't shipped in the
initial Phase 2 push; today's session's audit confirms 6 of 10 items
shipped and 4 (incl. these 3) outstanding.

## 5. Proposed fix

Three new jobs in `.github/workflows/ci.yml`, inserted after
`bandit-scan-addons` (matching its style — `runs-on: ubuntu-latest`,
fetch-depth 1 or 2, one-pass install + check):

### Job 1 — `lint-xml`

Runs `xmllint --noout` on every `.xml` under `custom-addons/` changed
in the PR (or in the push range). Uses `git diff --name-only
--diff-filter=ACMR <base>..<head>` to identify changed files. Catches
parse errors before the Docker build does.

### Job 2 — `lint-odoo-manifest`

For every `__manifest__.py` changed in the PR/push range:
- `ast.literal_eval` it — catches Python syntax errors and ensures
  the file is a pure-data dict (not a dynamic expression Odoo will
  refuse to load).
- Assert presence of required keys: `name`, `version`, `license`,
  `depends`, `installable`.
- Validate that `version` starts with a digit (loose, but catches
  empty strings and mis-edits).

### Job 3 — `gitleaks-scan`

Runs the `gitleaks` binary (installed from the official release —
avoids `gitleaks-action`'s org-license requirement) on the PR diff
range. `--redact` ensures any leaked value is replaced with `REDACTED`
in the log. Failing exit halts the PR.

## 6. Regression test

CI itself is the test. The PR's own validation:

- **Positive:** a separate test PR adds a deliberately-bad XML file +
  a deliberately-bad manifest + a deliberately-leaked fake API key;
  all three new jobs FAIL → PR is blocked. (Not part of this PR;
  optional follow-up.)
- **Negative (this PR):** the three new jobs PASS against the
  unchanged `custom-addons/` tree. No XML is malformed, no manifest is
  malformed, no secret is leaked.

## 7. Rollout

- Severity = medium → ride the next normal wave (merge to main as part
  of Phase 2 hardening).
- No feature flag — these are pure-CI additions.
- Expected outcomes:
  - 3 new GitHub Actions jobs visible in PR check rollups.
  - No change to PR latency for clean PRs (all 3 jobs are fast — sub-30s
    each on average; `gitleaks` parallel to existing jobs).
  - Any new manifest / XML defect, or any committed secret, is caught
    BEFORE the slow Docker-build cycle.
